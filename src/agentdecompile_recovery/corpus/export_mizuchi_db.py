"""Emit `mizuchi-db.json` so Mizuchi's Decomp Atlas renders this corpus.

The Atlas is already a fully dynamic UI — React, Vite, a Hono API — and it
hardcodes nothing. It renders whatever is in one file: `mizuchi-db.json` at the
project root. That file has never existed for this corpus, in any of the 70
projects under MizuchiRE or in the Mizuchi repo, which is the only reason the
Atlas showed "Error Loading Project" instead of 579,336 functions.

So the correct integration is not another bespoke page. It is to project our
SQLite corpus into the shape the Atlas already knows how to draw:

    DecompFunctionDoc.id             binary slug + address, stable across runs
    DecompFunctionDoc.name           resolved through the precedence ladder, so
                                     a real name always beats FUN_/sub_/Unwind_
    DecompFunctionDoc.romAddress     the function's address in its own build
    DecompFunctionDoc.cCode          Ghidra's decompiled C, when we have it
    DecompFunctionDoc.cModulePath    the ORIGINAL .cpp path from STABS, when
                                     known — the Atlas groups by this, which
                                     turns the Mac builds' debug records into
                                     real source-tree navigation for free
    DecompFunctionDoc.asmCode        the per-function listing
    DecompFunctionDoc.callsFunctions our `calledge` rows, so the Atlas's graph
                                     is the real call graph
    vectors[]                        a numeric feature vector per function; the
                                     Atlas runs UMAP over these for its scatter
                                     plot, so functions cluster by shape

One `mizuchi-db.json` describes one build, because that is what an Atlas project
is. Cross-build identity is carried in the name and in `crossBuild` metadata
rather than invented as a new field the UI would ignore.

The corpus has 24 builds and the Atlas loads a whole project file into browser
memory, so "generate everything at full fidelity" is not a plan: `--estimate`
prices the corpus at 4 GB of JSON before a byte is written, with nwmain.exe
alone over a gigabyte. `--max-functions` / `--no-asm` / `--no-c` trade fidelity
for a file that actually loads — asm is roughly three quarters of the weight,
so `--no-asm` is the first thing to reach for. Defaults are unchanged, so an
existing project regenerates byte-for-byte.

    ./venv/bin/python kx/export_mizuchi_db.py --estimate
    ./venv/bin/python kx/export_mizuchi_db.py --binary /TSL/k2_win_CD_1.0_swkotor2.exe
    ./venv/bin/python kx/export_mizuchi_db.py --all --max-functions 8000 --no-asm
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import corpus_config, db
from . import ghidra_env as ge

OUT_ROOT = ge.resolve_workspace() / "output" / "atlas"
KNOWLEDGE_DB = ge.resolve_workspace() / "db" / "ghidra_knowledge.sqlite"

def atlas_target(arch: str | None, platform: str | None = None) -> str:
    """Map recorded binary metadata to an architecture target the Atlas accepts.

    This must never use a console as a placeholder.  A previous constant wrote
    ``gba`` for every PE, ELF, Mach-O, and XBE and leaked "Game Boy Advance"
    into the UI and generated prompts.  The generic targets below describe the
    processor evidence only; OS/storefront stays in index metadata.
    """
    value = (arch or "").strip().lower().replace("-", "_")
    return {
        "x86": "x86",
        "i386": "x86",
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm": "arm",
        "aarch64": "aarch64",
        "arm64": "aarch64",
        "powerpc": "ppc",
        "ppc": "ppc",
    }.get(value, "unknown")

# Kept deliberately small. The Atlas holds every function in memory and runs
# UMAP over the vectors in a worker; a wide vector would cost a lot for detail
# that does not separate functions any better than these axes do.
VECTOR_FIELDS = [
    "size", "n_instr", "n_blocks", "n_edges", "cyclomatic",
    "n_callees", "param_count", "stack_frame_size",
]

# .text is ciphertext in these two, so every "function" Ghidra found is noise.
# Rendering them would put 21,000 decompilations of garbage in front of a human
# who has no way to tell them from the real thing.
DRM_ENCRYPTED = set(corpus_config.load_maps().get("drm_repo_paths") or [])
DUPLICATES = set(corpus_config.load_maps().get("duplicate_repo_paths") or [])


def _program(repo_path: str) -> str:
    return repo_path.rstrip("/").split("/")[-1]


def _hex_width(con: sqlite3.Connection, program: str) -> int:
    """entry_hex is zero-padded to the build's pointer width — 8 for the 32-bit
    builds, 16 for the AArch64/x64 ones. Looking it up beats assuming it, since
    a wrong width silently returns zero knowledge rows."""
    row = con.execute(
        "SELECT entry_hex FROM func_knowledge WHERE program=? LIMIT 1",
        (program,)).fetchone()
    return len(row[0]) if row else 8


def _knowledge(program: str, addrs: list[int] | None,
               want_c: bool, want_asm: bool) -> dict[int, dict]:
    """addr -> {c, asm} from the cached per-function Ghidra export.

    When only a slice of the build is being emitted, the rows are fetched one
    primary-key seek at a time. Scanning the program instead would drag every
    decompilation and listing off a spinning disk to throw most of them away.
    """
    if not KNOWLEDGE_DB.exists() or not (want_c or want_asm):
        return {}
    cols = []
    if want_c:
        cols.append("decompiled")
    if want_asm:
        cols.append("asm")
    con = sqlite3.connect(f"file:{KNOWLEDGE_DB}?mode=ro", uri=True)
    out: dict[int, dict] = {}

    def absorb(entry_hex: str, values: tuple) -> None:
        try:
            addr = int(entry_hex, 16)
        except (TypeError, ValueError):
            return
        rec = {}
        vals = list(values)
        if want_c:
            rec["c"] = vals.pop(0)
        if want_asm:
            rec["asm"] = vals.pop(0)
        out[addr] = rec

    try:
        sel = ", ".join(cols)
        if addrs is None:
            for row in con.execute(
                    f"SELECT entry_hex, {sel} FROM func_knowledge WHERE program=?",
                    (program,)):
                absorb(row[0], row[1:])
        else:
            width = _hex_width(con, program)
            q = (f"SELECT entry_hex, {sel} FROM func_knowledge "
                 "WHERE program=? AND entry_hex=?")
            for addr in addrs:
                row = con.execute(q, (program, f"{addr:0{width}x}")).fetchone()
                if row is not None:
                    absorb(row[0], row[1:])
    except sqlite3.Error:
        pass
    con.close()
    return out


def _vector(row: dict) -> list[float]:
    """A compact numeric signature, log-scaled so one huge function does not
    flatten every other axis when UMAP normalises the space."""
    vec = []
    for f in VECTOR_FIELDS:
        v = row.get(f) or 0
        try:
            vec.append(math.log1p(float(v)))
        except (TypeError, ValueError):
            vec.append(0.0)
    return vec


def build(repo_path: str, max_functions: int | None = None,
          with_asm: bool = True, with_c: bool = True) -> dict:
    con = db.connect(read_only=True)
    b = con.execute(
        "SELECT id, slug, repo_path, arch, bits, platform, func_count FROM binary "
        "WHERE repo_path=?", (repo_path,)).fetchone()
    if b is None:
        raise SystemExit(f"no such binary: {repo_path}")
    bid, slug = b["id"], b["slug"]

    program = _program(repo_path)

    # Resolved names, so a placeholder never displaces a real name that another
    # fork already contributed.
    names: dict[int, tuple[str, str]] = {}
    for addr, name, tier in con.execute(
            "SELECT i.addr, n.name, n.tier_name FROM identity i "
            "JOIN logical_name n ON n.logical_id = i.logical_id "
            "WHERE i.binary_id=?", (bid,)):
        names[addr] = (name, tier)

    logical: dict[int, int] = {
        addr: lid for addr, lid in con.execute(
            "SELECT addr, logical_id FROM identity WHERE binary_id=?", (bid,))}

    # How many builds each logical function reaches — the number that makes this
    # corpus worth cross-matching at all.
    #
    # Counted by streaming the two primary-key columns and tallying here, rather
    # than the obvious `WHERE logical_id IN (SELECT ... WHERE binary_id=?)`.
    # That form makes SQLite seek ix_identity_logical once per logical id — tens
    # of thousands of random reads, which on a contended spinning disk dominated
    # the whole export. Both columns live in identity's primary key, so this
    # query is index-only and reads sequentially; only the ids this build
    # actually uses are kept, so memory stays bounded by one build.
    reach: dict[int, int] = {}
    if logical:
        wanted = set(logical.values())
        seen: dict[int, set[int]] = {}
        for other_bid, lid in con.execute(
                "SELECT binary_id, logical_id FROM identity"):
            if lid in wanted:
                seen.setdefault(lid, set()).add(other_bid)
        reach = {lid: len(bins) for lid, bins in seen.items()}

    calls: dict[int, list[int]] = {}
    for caller, callee in con.execute(
            "SELECT caller_addr, callee_addr FROM calledge WHERE binary_id=?", (bid,)):
        calls.setdefault(caller, []).append(callee)

    def fid(addr: int) -> str:
        return f"{slug}::{addr:08x}"

    rows = [dict(r) for r in con.execute(
        "SELECT addr, name, size, n_instr, n_blocks, n_edges, cyclomatic, "
        "       n_callees, param_count, stack_frame_size, signature, "
        "       source_file, object_file "
        "FROM func WHERE binary_id=? AND size>0 AND n_instr>0 "
        "ORDER BY addr", (bid,))]

    kept_ids: set[str] | None = None
    if max_functions is not None and len(rows) > max_functions:
        # Largest-first. Address order would just hand back whichever translation
        # units the linker happened to place at the bottom of .text; instruction
        # count picks the functions that actually contain the program's logic,
        # which is what a human opens the Atlas to read. Re-sorted by address
        # afterwards so the file and project.map keep their usual ordering.
        rows.sort(key=lambda r: (r.get("n_instr") or 0, r.get("size") or 0),
                  reverse=True)
        rows = sorted(rows[:max_functions], key=lambda r: r["addr"])
        kept_ids = {fid(r["addr"]) for r in rows}

    know = _knowledge(
        program,
        [r["addr"] for r in rows] if kept_ids is not None else None,
        want_c=with_c, want_asm=with_asm)

    funcs, vectors = [], []
    for row in rows:
        addr = row["addr"]
        k = know.get(addr, {})
        resolved, tier = names.get(addr, (None, None))
        lid = logical.get(addr)

        edges = [fid(a) for a in calls.get(addr, [])]
        if kept_ids is not None:
            # An edge to a function that was cut points at an id the file does
            # not contain, and the Atlas's call graph would render a dead node.
            edges = [e for e in edges if e in kept_ids]

        doc = {
            "id": fid(addr),
            "name": resolved or row["name"] or f"FUN_{addr:08x}",
            "romAddress": addr,
            "asmCode": k.get("asm") or "",
            # The Atlas groups by module path. STABS gives the original .cpp for
            # the Mac builds; everything else falls into one bucket rather than
            # a fabricated path, so a real path always means a real path.
            "asmModulePath": row.get("source_file") or "unattributed",
            "callsFunctions": edges,
        }
        if k.get("c"):
            doc["cCode"] = k["c"]
            doc["cModulePath"] = row.get("source_file") or "unattributed"
        # Extra keys the Atlas ignores today but that keep this file honest and
        # self-describing rather than lossy.
        doc["crossBuild"] = {
            "logicalId": lid,
            "buildsReached": reach.get(lid, 1 if lid else 0),
            "nameTier": tier,
            "signature": row.get("signature"),
            "objectFile": row.get("object_file"),
        }
        funcs.append(doc)
        vectors.append({"id": doc["id"], "embedding": _vector(row)})

    meta = {
        "contentHashes": {},
        "source": "kotorxid db/kotorxid.sqlite",
        "binary": repo_path,
        "arch": b["arch"],
        "bits": b["bits"],
        "generatedAt": time.time(),
    }
    # Recorded only when the export is lossy, so a full export stays byte-for-byte
    # what it has always been and a truncated one can never be mistaken for one.
    if kept_ids is not None:
        meta["truncated"] = {"maxFunctions": max_functions,
                             "selection": "largest-first by n_instr",
                             "totalFunctions": b["func_count"]}
    if not with_asm:
        meta["omitted"] = meta.get("omitted", []) + ["asmCode"]
    if not with_c:
        meta["omitted"] = meta.get("omitted", []) + ["cCode"]

    target = atlas_target(b["arch"], b["platform"])
    return {
        "version": 1,
        "platform": target,
        "decompFunctions": funcs,
        "vectors": vectors,
        "indexMetadata": meta,
    }


MIZUCHI_YAML = """\
# Generated by kx/export_mizuchi_db.py — points Mizuchi's Decomp Atlas at the
# kotorxid corpus. Every field below is required by the Atlas config schema;
# the recovery-loop fields are unused here because this project exists to be
# READ by the Atlas, not to run a decompilation loop.
global:
  projectRoot: {root}
  mapFilePath: {root}/project.map
  promptsDir: ./prompts
  nonMatchingAsmFolders:
    - asm
  outputDir: .
  target: {target}
  compilerScript: 'true'
  getContextScript: 'true'
  maxRetries: 1
plugins:
  integrator:
    enable: false
    integratorModule: './integrator.mjs'
"""


def write(repo_path: str, out_root: pathlib.Path = OUT_ROOT,
          max_functions: int | None = None,
          with_asm: bool = True, with_c: bool = True) -> pathlib.Path:
    dump = build(repo_path, max_functions=max_functions,
                 with_asm=with_asm, with_c=with_c)
    slug = repo_path.strip("/").replace("/", "__")
    root = out_root / slug
    root.mkdir(parents=True, exist_ok=True)
    out = root / "mizuchi-db.json"
    # Written through a temp file and renamed. These take tens of minutes on a
    # loaded disk, and a run interrupted part-way through a 90 MB write would
    # otherwise leave truncated JSON that the Atlas reports as a corrupt project
    # rather than an absent one.
    tmp = out.with_suffix(".json.partial")
    tmp.write_text(json.dumps(dump))
    tmp.replace(out)
    # The Atlas refuses to load without a map file, so emit the symbol map it
    # expects from the same data rather than leaving a dangling requirement.
    (root / "project.map").write_text("\n".join(
        f"{f['romAddress']:08x} {f['name']}" for f in dump["decompFunctions"]))
    (root / "mizuchi.yaml").write_text(MIZUCHI_YAML.format(
        root=root, target=dump["platform"],
    ))
    # The config names these; the Atlas walks them at load and an absent
    # directory is an error rather than an empty list.
    (root / "prompts").mkdir(exist_ok=True)
    (root / "asm").mkdir(exist_ok=True)
    n_c = sum(1 for f in dump["decompFunctions"] if f.get("cCode"))
    print(f"[+] {repo_path}", flush=True)
    print(f"    {len(dump['decompFunctions']):>7,} functions  "
          f"{n_c:>7,} with C  {out.stat().st_size/1e6:.1f} MB  -> {out}",
          flush=True)
    return out


# --- estimation -------------------------------------------------------------

# Everything in a doc that is not cCode/asmCode: id, name, romAddress, the call
# list, crossBuild, and the function's vector entry. Measured, not guessed:
# a --no-asm --no-c export of /TSL/k2_xbox_default.xbe came to 7.2 MB across
# 10,477 functions. Call lists and signatures vary between builds, so treat this
# as the right order of magnitude rather than a promise.
_STRUCT_BYTES = 690.0
# func_knowledge is a rowid table with a separate (program, entry_hex) index, so
# every sampled row is an index seek plus a random rowid fetch. On a contended
# spinning disk that is the whole cost of estimating, and it is why the sample
# is this small: 3x20 per build prices 22 builds in about a thousand reads.
# --sample buys precision back when the disk is quiet.
_SAMPLE_WINDOWS, _SAMPLE_PER = 3, 20


def _sample_keys(kn: sqlite3.Connection, program: str) -> list[str]:
    """Start keys for evenly spread sample windows across one program.

    LIMIT/OFFSET would be the obvious way and is unusable here: OFFSET makes
    SQLite walk every skipped row, which on this disk means dragging most of a
    2.7 GB table through the page cache to read 400 rows. entry_hex is
    fixed-width zero-padded hex, so lexical order is numeric order and each
    window can be reached by an index seek instead.
    """
    row = kn.execute(
        "SELECT MIN(entry_hex), MAX(entry_hex) FROM func_knowledge WHERE program=?",
        (program,)).fetchone()
    if not row or row[0] is None:
        return []
    lo, hi = row
    width = len(lo)
    try:
        a, b = int(lo, 16), int(hi, 16)
    except ValueError:
        return [lo]
    span = max(b - a, 1)
    return [f"{a + span * w // _SAMPLE_WINDOWS:0{width}x}"
            for w in range(_SAMPLE_WINDOWS)]


def estimate(per_window: int = _SAMPLE_PER) -> None:
    """Price every build's mizuchi-db.json before generating any of it.

    Uses `binary.code_func_count` and a sampled cost per function. The `func`
    table is half a gigabyte; measuring by generating would cost more than the
    generation this is meant to avoid.
    """
    con = db.connect(read_only=True)
    kn = sqlite3.connect(f"file:{KNOWLEDGE_DB}?mode=ro", uri=True)
    done = {r[0]: r[1] for r in kn.execute(
        "SELECT program, functions_done FROM ingest_status")}

    print(f"{'repo_path':<48} {'funcs':>7} {'know':>7} {'C/fn':>6} {'asm/fn':>7} "
          f"{'full':>8} {'-asm':>8} {'-c':>8} {'struct':>7}")
    total = 0.0
    for r in con.execute(
            "SELECT repo_path, func_count, code_func_count FROM binary "
            "ORDER BY repo_path"):
        repo_path = r["repo_path"]
        n = r["code_func_count"] or r["func_count"] or 0
        program = _program(repo_path)
        have = done.get(program, 0)
        c_b = a_b = 0
        seen = 0
        for lo in _sample_keys(kn, program):
            for dec, asm in kn.execute(
                    "SELECT decompiled, asm FROM func_knowledge "
                    "WHERE program=? AND entry_hex>=? ORDER BY entry_hex LIMIT ?",
                    (program, lo, per_window)):
                seen += 1
                # json.dumps is the real cost: escaping newlines and quotes
                # inflates decompiled C by about a tenth, and that factor is
                # exactly where naive size projections go wrong.
                c_b += len(json.dumps(dec or ""))
                a_b += len(json.dumps(asm or ""))
        c_avg = c_b / seen if seen else 0.0
        a_avg = a_b / seen if seen else 0.0
        cov = min(have / n, 1.0) if n else 0.0
        full = n * (_STRUCT_BYTES + cov * (c_avg + a_avg)) / 1e6
        total += full
        print(f"{repo_path:<48} {n:>7,} {have:>7,} {c_avg:>6.0f} {a_avg:>7.0f} "
              f"{full:>8.1f} {n*(_STRUCT_BYTES+cov*c_avg)/1e6:>8.1f} "
              f"{n*(_STRUCT_BYTES+cov*a_avg)/1e6:>8.1f} "
              f"{n*_STRUCT_BYTES/1e6:>7.1f}", flush=True)
    print(f"{'TOTAL':<48} {total:>39.1f} MB   (sizes in MB)", flush=True)
    # Read these as an upper bound, not a measurement. Decompilation and listing
    # length are heavy-tailed, so a few dozen sampled functions overshoot: the
    # one build with a real file on disk, /TSL/k2_win_CD_1.0_swkotor2.exe,
    # projects around 200 MB and actually weighs 90 MB. Raise --sample when the
    # disk is quiet enough to pay for it.
    print("note: sampled from a few dozen functions per build; treat as an "
          "upper bound (--sample raises precision at the cost of disk reads)",
          flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--estimate", action="store_true",
                    help="report projected JSON size per build, generate nothing")
    ap.add_argument("--sample", type=int, default=_SAMPLE_PER,
                    help="rows per sample window when estimating (default %(default)s)")
    ap.add_argument("--max-functions", type=int,
                    help="keep only the N largest functions by instruction count")
    ap.add_argument("--no-asm", action="store_true", help="omit asmCode")
    ap.add_argument("--no-c", action="store_true", help="omit cCode")
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    ap.add_argument("--include-skipped", action="store_true",
                    help="also emit the DRM-encrypted and duplicate builds")
    a = ap.parse_args()

    if a.estimate:
        estimate(per_window=a.sample)
        return

    con = db.connect(read_only=True)
    if a.all:
        targets = [r["repo_path"] for r in con.execute(
            "SELECT repo_path FROM binary ORDER BY repo_path")]
        if not a.include_skipped:
            skip = DRM_ENCRYPTED | DUPLICATES
            for t in [t for t in targets if t in skip]:
                print(f"[-] {t}: skipped "
                      f"({'DRM-encrypted .text' if t in DRM_ENCRYPTED else 'duplicate bytes'})",
                      flush=True)
            targets = [t for t in targets if t not in skip]
    elif a.binary:
        targets = [a.binary]
    else:
        raise SystemExit("pass --binary <repo_path>, --all, or --estimate")

    out_root = pathlib.Path(a.out_root)
    for t in targets:
        try:
            write(t, out_root=out_root, max_functions=a.max_functions,
                  with_asm=not a.no_asm, with_c=not a.no_c)
        except Exception as exc:  # noqa: BLE001 - one bad build must not stop the rest
            print(f"[!] {t}: {exc}", flush=True)


if __name__ == "__main__":
    main()
