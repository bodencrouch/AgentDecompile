"""Cascade determinism harness (plan U5c gate b / U28 e).

Proves — or disproves — that the identity cascade (``logical.build`` →
``propagate.run_pair`` per pair → ``propagate.downgrade_named_conflicts`` →
``propagate.bind_identities`` → ``propagate.dedupe_identity_addrs``) is a pure
function of the ``binary`` / ``func`` / ``calledge`` rows, independent of row
insertion order and SQLite physical layout.

Procedure:

1. Snapshot the fixture store's ``binary``, ``func`` and ``calledge`` rows.
2. Run ``canonical``: fresh DB file, rows inserted in canonical order, cascade.
3. Run ``reingest`` (U28 e): fresh DB file, rows inserted in a seeded shuffled
   order (``func`` rows get fresh rowids so the shuffle is physical), cascade.
4. Run ``vacuum_analyze`` (U5c b): same shuffled insert, then ``VACUUM`` and
   ``ANALYZE`` before the cascade, so the planner sees different statistics.
5. Dump ``identity``, ``match`` and ``logical_function`` from every run in a
   canonical sorted form and byte-compare against ``canonical``. The first
   differing row is named.

Both perturbations are kept because they reach different code paths: with
``ANALYZE`` statistics the planner tends to drive the unordered SELECTs through
``ix_func_bin_addr`` (which happens to return canonical order), while a plain
re-ingest keeps the rowid scan and exposes the insertion order directly.

No Ghidra, no real binaries: the fixture is synthetic and generated from a
seed by :func:`generate_fixture`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import sqlite3
import sys
from dataclasses import dataclass, field

from . import canon, logical, propagate, store
from .fingerprint_hashes import attach_hashes

FIXTURE_TABLES = ("binary", "func", "calledge")
OUTPUT_TABLES = ("identity", "match", "logical_function")
RUN = "determinism"
FIXTURE_SEED = 7
FIXTURE_JSON_NAME = "cascade_fixture.json"


@dataclass
class TableResult:
    identical: bool
    rows_a: int
    rows_b: int
    first_diff: str | None = None
    note: str | None = None


@dataclass
class HarnessResult:
    """``tables[run_label][table]`` compares that perturbed run to ``canonical``."""

    identical: bool
    first_diff: str | None
    tables: dict[str, dict[str, TableResult]] = field(default_factory=dict)
    seed: int = 0
    cascades: dict[str, dict] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "identical": self.identical,
            "first_diff": self.first_diff,
            "seed": self.seed,
            "tables": {
                run: {
                    name: {
                        "identical": t.identical,
                        "rows_a": t.rows_a,
                        "rows_b": t.rows_b,
                        "first_diff": t.first_diff,
                        "note": t.note,
                    }
                    for name, t in per_table.items()
                }
                for run, per_table in self.tables.items()
            },
            "cascades": self.cascades,
        }


# --------------------------------------------------------------------------
# Snapshot / load
# --------------------------------------------------------------------------


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f"PRAGMA table_info({table})")]


def snapshot(con: sqlite3.Connection) -> dict[str, list[dict]]:
    """Canonically ordered copy of the fixture tables.

    ``func.id`` is dropped: nothing in the cascade reads it, and re-assigning it
    on insert is what lets a shuffled load change physical row order.
    ``binary.id`` is kept because every output table carries ``binary_id``.
    """
    orders = {
        "binary": "id",
        "func": "binary_id, addr",
        "calledge": "binary_id, caller_addr, callee_addr",
    }
    out: dict[str, list[dict]] = {}
    for table in FIXTURE_TABLES:
        cols = _columns(con, table)
        if table == "func":
            cols = [c for c in cols if c != "id"]
        sel = ", ".join(cols)
        rows = con.execute(f"SELECT {sel} FROM {table} ORDER BY {orders[table]}").fetchall()
        out[table] = [dict(zip(cols, tuple(r))) for r in rows]
    return out


def load_snapshot(
    con: sqlite3.Connection,
    snap: dict[str, list[dict]],
    *,
    rng: random.Random | None = None,
) -> None:
    """Insert snapshot rows. With *rng*, every table's rows are shuffled."""
    for table in FIXTURE_TABLES:
        rows = list(snap.get(table, ()))
        if rng is not None:
            rng.shuffle(rows)
        if not rows:
            continue
        cols = sorted({c for r in rows for c in r})
        marks = ",".join("?" for _ in cols)
        con.executemany(
            f"INSERT INTO {table}({', '.join(cols)}) VALUES({marks})",
            [tuple(r.get(c) for c in cols) for r in rows],
        )
    con.commit()


# --------------------------------------------------------------------------
# Cascade
# --------------------------------------------------------------------------


def run_cascade(con: sqlite3.Connection, run: str = RUN) -> dict:
    """The existing match → bind cascade, exactly as the CLIs sequence it."""
    summary: dict = {"logical": logical.build(con)}
    bins = con.execute("SELECT id, repo_path FROM binary ORDER BY id").fetchall()
    pairs = [
        (str(a["repo_path"]), str(b["repo_path"]), f"{a['id']}->{b['id']}")
        for i, a in enumerate(bins)
        for b in bins[i + 1:]
    ]
    receipts = propagate.run_registry_pairs(con, pairs, run=run)
    summary["pairs"] = [
        {"src": r["src"], "dst": r["dst"], "counts": r["counts"]} for r in receipts
    ]
    summary["deduped"] = propagate.dedupe_identity_addrs(con)
    con.commit()
    return summary


# --------------------------------------------------------------------------
# Dump / compare
# --------------------------------------------------------------------------


def _canonical_lines(con: sqlite3.Connection, table: str, *, drop: tuple[str, ...] = ()) -> list[str]:
    cols = [c for c in _columns(con, table) if c not in drop]
    sel = ", ".join(cols)
    rows = con.execute(f"SELECT {sel} FROM {table}").fetchall()
    lines = [
        json.dumps(dict(zip(cols, tuple(r))), sort_keys=True, separators=(",", ":"))
        for r in rows
    ]
    lines.sort()
    return lines


def dump_tables(con: sqlite3.Connection) -> dict[str, list[str]]:
    out = {table: _canonical_lines(con, table) for table in OUTPUT_TABLES}
    # Same rows minus the autoincrement id, so the report shows whether a
    # `match` difference is only rowid assignment or a real content change.
    out["match_no_id"] = _canonical_lines(con, "match", drop=("id",))
    return out


def _normalize_evidence(line: str) -> str:
    try:
        row = json.loads(line)
    except ValueError:
        return line
    ev = row.get("evidence")
    if isinstance(ev, str):
        try:
            row["evidence"] = json.dumps(json.loads(ev), sort_keys=True, separators=(",", ":"))
        except ValueError:
            pass
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def _strip_ids(lines: list[str]) -> list[str]:
    """Rows with ``id``/``logical_id`` removed: tells relabeling from content change."""
    out = []
    for line in lines:
        row = json.loads(line)
        row.pop("id", None)
        row.pop("logical_id", None)
        out.append(json.dumps(row, sort_keys=True, separators=(",", ":")))
    out.sort()
    return out


def compare_dumps(a: dict[str, list[str]], b: dict[str, list[str]]) -> dict[str, TableResult]:
    results: dict[str, TableResult] = {}
    for table in list(OUTPUT_TABLES) + ["match_no_id"]:
        la, lb = a[table], b[table]
        first = None
        for i, (x, y) in enumerate(zip(la, lb)):
            if x != y:
                first = f"{table} row {i}:\n- {x}\n+ {y}"
                break
        if first is None and len(la) != len(lb):
            i = min(len(la), len(lb))
            extra = la[i] if len(la) > len(lb) else lb[i]
            side = "-" if len(la) > len(lb) else "+"
            first = f"{table} row count {len(la)} vs {len(lb)}; first unmatched:\n{side} {extra}"
        note = None
        if first is not None and table.startswith("match"):
            na = sorted(_normalize_evidence(x) for x in la)
            nb = sorted(_normalize_evidence(y) for y in lb)
            note = (
                "difference is only JSON key order inside match.evidence"
                if na == nb
                else "difference survives sort_keys normalization of match.evidence"
            )
        elif first is not None:
            note = (
                "difference is only id/logical_id numbering"
                if _strip_ids(la) == _strip_ids(lb)
                else "difference survives id/logical_id relabeling (content differs)"
            )
        results[table] = TableResult(first is None, len(la), len(lb), first, note)
    return results


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------


def _fresh(path: pathlib.Path) -> sqlite3.Connection:
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = pathlib.Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    return store.connect(path)


PERTURBED_RUNS = ("reingest", "vacuum_analyze")


def _run_once(path: pathlib.Path, snap: dict[str, list[dict]], *, seed: int | None, repack: bool) -> tuple[dict, dict[str, list[str]]]:
    con = _fresh(path)
    try:
        load_snapshot(con, snap, rng=None if seed is None else random.Random(seed))
        if repack:
            con.commit()
            con.execute("VACUUM")
            con.execute("ANALYZE")
            con.commit()
        cascade = run_cascade(con)
        return cascade, dump_tables(con)
    finally:
        con.close()


def run_harness(fixture_store: pathlib.Path | str, seed: int, *, work_dir: pathlib.Path | str | None = None) -> HarnessResult:
    """Run the cascade from *fixture_store* under each layout and byte-compare."""
    fixture_store = pathlib.Path(fixture_store)
    work = pathlib.Path(work_dir) if work_dir is not None else fixture_store.parent
    src = store.connect(fixture_store)
    try:
        snap = snapshot(src)
    finally:
        src.close()

    cascades: dict[str, dict] = {}
    cascades["canonical"], dump_a = _run_once(work / f"{fixture_store.stem}.canonical.sqlite", snap, seed=None, repack=False)
    tables: dict[str, dict[str, TableResult]] = {}
    for label in PERTURBED_RUNS:
        cascades[label], dump_b = _run_once(
            work / f"{fixture_store.stem}.{label}.sqlite", snap, seed=seed, repack=(label == "vacuum_analyze"),
        )
        tables[label] = compare_dumps(dump_a, dump_b)

    first_diff = None
    for label in PERTURBED_RUNS:
        for name in OUTPUT_TABLES:
            t = tables[label][name]
            if t.first_diff:
                first_diff = f"[{label}] {t.first_diff}" + (f"\n  note: {t.note}" if t.note else "")
                break
        if first_diff:
            break
    identical = all(tables[label][name].identical for label in PERTURBED_RUNS for name in OUTPUT_TABLES)
    return HarnessResult(identical, first_diff, tables, seed, cascades)


# --------------------------------------------------------------------------
# Synthetic fixture
# --------------------------------------------------------------------------

BUILD_SLUGS = ("build-a", "build-b", "build-c")
MNEMS = ("mov", "add", "sub", "cmp", "jz", "jnz", "call", "ret", "push", "pop", "lea", "xor", "test", "jmp")


def _digest(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def _cfg(n_blocks: int) -> tuple[list[int], list[list[int]]]:
    nodes = list(range(n_blocks))
    edges = [[i, i + 1] for i in range(n_blocks - 1)]
    if n_blocks >= 3:
        edges.append([0, n_blocks - 1])
    return nodes, edges


def _mnem(rng: random.Random, n_instr: int) -> dict[str, int]:
    picks = rng.sample(MNEMS, 6)
    counts = {m: 1 for m in picks}
    for _ in range(n_instr - 6):
        counts[rng.choice(picks)] += 1
    return dict(sorted(counts.items()))


def _feature(rng: random.Random, tag: str, *, n_instr: int, strings: list[str], consts: list[int], ext_calls: list[str], source_file: str | None) -> dict:
    """Shared feature body for one function *kind*; identical across builds."""
    n_blocks = max(1, n_instr // 6)
    nodes, edges = _cfg(n_blocks)
    return {
        "size": n_instr * 3,
        "n_instr": n_instr,
        "n_blocks": n_blocks,
        "n_edges": len(edges),
        "back_edges": 0,
        "cyclomatic": len(edges) - n_blocks + 2,
        "indirect_calls": 0,
        "data_refs": len(consts),
        "mnem": _mnem(rng, n_instr),
        "strings": sorted(strings),
        "consts": sorted(consts),
        "ext_calls": sorted(ext_calls),
        "block_hashes": [_digest("blk", tag, i)[:16] for i in range(n_blocks)],
        "cfg_nodes": nodes,
        "cfg_edges": edges,
        "source_file": source_file,
        "param_count": len(consts) % 3,
    }


def _roster(rng: random.Random) -> list[dict]:
    """Per-build function roster. Each entry: kind, key, feature, name spec."""
    roster: list[dict] = []
    # 12 authentic named hubs: channel I anchors, callgraph parents, and
    # a per-build plate line so logical.best_signature depends on member order.
    classes = ("Alpha", "Beta", "Delta", "Kappa")
    for k in range(12):
        cls = classes[k % len(classes)]
        method = f"step{k}"
        roster.append({
            "kind": "hub", "key": f"hub{k}", "cls": cls, "method": method,
            "arity": k % 3,
            "feature": _feature(rng, f"hub{k}", n_instr=24 + 2 * k, strings=[f"hub-text-{k:02d}"], consts=[0x1000 + 97 * k], ext_calls=[f"ext_{k % 4}"], source_file=f"unit_{k % 5}.c"),
        })
    # 3 names duplicated within every build with identical features:
    # resolve_ambiguous ranks tie, slots tie on n_instr, pair scores tie.
    for k, method in enumerate(("update", "render", "close")):
        feat = _feature(rng, f"dup{k}", n_instr=16 + k, strings=[f"dup-text-{k}"], consts=[0x2000 + k], ext_calls=[], source_file=f"widget_{k}.c")
        for copy in range(2):
            roster.append({"kind": "dup", "key": f"dup{k}_{copy}", "cls": "Widget", "method": method, "arity": 1, "feature": dict(feat)})
    # 12 unnamed callees, one per hub. Callee k and k+6 collide on every
    # hash so no H anchor forms; only callgraph propagation binds them.
    for k in range(12):
        base = k % 6
        roster.append({
            "kind": "callee", "key": f"callee{k}", "hub": f"hub{k}",
            "feature": _feature(rng, f"callee{base}", n_instr=12 + base, strings=[], consts=[base + 1], ext_calls=[], source_file=None),
        })
    # 3 contested destinations (D3): the unique callee of a named hub carries
    # a different authentic name in build-a and build-b and none in build-c.
    for k, method in enumerate(("one", "two", "three")):
        roster.append({
            "kind": "contest", "key": f"contest{k}", "hub": f"hub{9 + k}",
            "names": {"build-a": (f"Gamma{k}", "left"), "build-b": (f"Gamma{k}", "right"), "build-c": None},
            "feature": _feature(rng, f"contest{k}", n_instr=14 + k, strings=[], consts=[k + 7], ext_calls=[], source_file=None),
        })
    # Fuzzy first-wins race (D4): two same-name sources in build-a with
    # identical rich features, one unnamed target elsewhere.
    for k in range(2):
        feat = _feature(rng, f"tie{k}", n_instr=30 + k, strings=[f"tie-text-{k}-long-enough"], consts=[0x3000 + k, 0x3100 + k], ext_calls=[f"ext_tie{k}"], source_file=f"tie_{k}.c")
        for copy in range(2):
            roster.append({"kind": "tie", "key": f"tie{k}_{copy}", "cls": "Omega", "method": f"tie{k}", "arity": 2, "feature": dict(feat)})
    # 6 unnamed, unique-everywhere fillers: stable H/X anchors.
    for k in range(6):
        roster.append({
            "kind": "filler", "key": f"filler{k}",
            "feature": _feature(rng, f"filler{k}", n_instr=20 + 3 * k, strings=[f"filler-text-{k:02d}"], consts=[0x4000 + 131 * k], ext_calls=[f"ext_{k % 3}"], source_file=f"fill_{k}.c"),
        })
    return roster


def _present(entry: dict, slug: str) -> bool:
    if entry["kind"] == "tie":
        # build-a keeps both copies; other builds carry one unnamed target.
        return slug == "build-a" or entry["key"].endswith("_0")
    return True


def _name_for(entry: dict, slug: str, addr: int) -> dict:
    kind = entry["kind"]
    if kind in {"hub", "dup"} or (kind == "tie" and slug == "build-a"):
        cls, method, arity = entry["cls"], entry["method"], entry["arity"]
        params = [f"p{i}" for i in range(arity)]
        plate = f"int {cls}::{method}({', '.join(f'int {p}' for p in params)}) [{slug}]"
        c = canon.canonicalize(f"{cls}::{method}", None, plate, dm_name=method, dm_namespace=cls, dm_params=["int"] * arity)
        return {"name": f"{cls}::{method}", "namespace": cls, "plate": plate, "signature": plate.split(" [")[0], "source": "IMPORTED", **c}
    if kind == "contest" and entry["names"].get(slug):
        cls, method = entry["names"][slug]
        plate = f"void {cls}::{method}() [{slug}]"
        c = canon.canonicalize(f"{cls}::{method}", None, plate, dm_name=method, dm_namespace=cls, dm_params=[])
        return {"name": f"{cls}::{method}", "namespace": cls, "plate": plate, "signature": plate.split(" [")[0], "source": "IMPORTED", **c}
    c = canon.canonicalize(f"FUN_{addr:08x}")
    return {"name": f"FUN_{addr:08x}", "namespace": None, "plate": None, "signature": None, "source": "ANALYSIS", **c}


def generate_fixture(seed: int = FIXTURE_SEED) -> dict[str, list[dict]]:
    """Deterministic synthetic corpus: 3 builds, >=30 functions each, ties on purpose."""
    rng = random.Random(seed)
    roster = _roster(rng)
    binaries: list[dict] = []
    funcs: list[dict] = []
    edges: list[dict] = []
    for bid, slug in enumerate(BUILD_SLUGS, start=1):
        binaries.append({
            "id": bid, "repo_path": f"/fixture/{slug}", "slug": slug, "game": "g0",
            "platform": "p0", "variant": None, "language_id": "l0", "arch": "a32", "bits": 32,
            "format": "f0", "md5": None, "image_base": 0x400000, "func_count": None,
            "named_count": None, "role": None, "recovery_family": "family-0",
            "content_sha256": _digest("image", slug),
        })
        # Per-build address layout: a fixed permutation so addr order differs
        # from roster order and from the other builds.
        order = list(range(len(roster)))
        random.Random(seed * 100 + bid).shuffle(order)
        addr_of: dict[str, int] = {}
        for pos, idx in enumerate(order):
            entry = roster[idx]
            if _present(entry, slug):
                addr_of[entry["key"]] = 0x401000 + 0x40 * pos
        for entry in roster:
            if entry["key"] not in addr_of:
                continue
            addr = addr_of[entry["key"]]
            feat = entry["feature"]
            row = {
                "binary_id": bid, "addr": addr, "is_thunk": 0, "thunked_to": None,
                "calling_convention": "cc0", "return_type": "int",
                "stack_frame_size": 16, "stack_param_size": 4 * feat["param_count"], "stack_local_size": 8,
                "ranges": 1, "n_callees": 0, "object_file": None, "symbol_provenance": None,
                **{k: v for k, v in feat.items()},
            }
            row.update(_name_for(entry, slug, addr))
            row.pop("canon_params", None)
            row = attach_hashes(row)
            funcs.append(row)
        # Call graph: hub k -> callee k (unique unmatched callee), hub k -> hub k+1,
        # hub 9..11 -> contest 0..2, hub k -> filler k%6 (anchored by hash first).
        by_key = addr_of
        for entry in roster:
            if entry["kind"] in {"callee", "contest"} and entry["key"] in by_key:
                edges.append({"binary_id": bid, "caller_addr": by_key[entry["hub"]], "callee_addr": by_key[entry["key"]]})
        for k in range(12):
            edges.append({"binary_id": bid, "caller_addr": by_key[f"hub{k}"], "callee_addr": by_key[f"hub{(k + 1) % 12}"]})
            edges.append({"binary_id": bid, "caller_addr": by_key[f"hub{k}"], "callee_addr": by_key[f"filler{k % 6}"]})
        callee_counts: dict[int, int] = {}
        for e in edges:
            if e["binary_id"] == bid:
                callee_counts[e["caller_addr"]] = callee_counts.get(e["caller_addr"], 0) + 1
        for row in funcs:
            if row["binary_id"] == bid:
                row["n_callees"] = callee_counts.get(row["addr"], 0)
    for row in funcs:
        for col in ("mnem", "strings", "consts", "ext_calls", "block_hashes", "cfg_nodes", "cfg_edges"):
            row[col] = store.j(row[col])
    funcs.sort(key=lambda r: (r["binary_id"], r["addr"]))
    edges.sort(key=lambda r: (r["binary_id"], r["caller_addr"], r["callee_addr"]))
    return {"binary": binaries, "func": funcs, "calledge": edges}


def build_fixture_store(path: pathlib.Path | str, snap: dict[str, list[dict]]) -> pathlib.Path:
    path = pathlib.Path(path)
    con = _fresh(path)
    try:
        load_snapshot(con, snap)
    finally:
        con.close()
    return path


def fixture_json_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "determinism" / FIXTURE_JSON_NAME


def dump_fixture_json(snap: dict[str, list[dict]]) -> str:
    """One row per line, null columns omitted (``load_snapshot`` restores them)."""
    parts = ["{"]
    for ti, table in enumerate(FIXTURE_TABLES):
        parts.append(f' "{table}": [')
        rows = snap[table]
        for ri, row in enumerate(rows):
            comma = "," if ri + 1 < len(rows) else ""
            slim = {k: v for k, v in row.items() if v is not None}
            parts.append("  " + json.dumps(slim, sort_keys=True, separators=(",", ":")) + comma)
        parts.append(" ]" + ("," if ti + 1 < len(FIXTURE_TABLES) else ""))
    parts.append("}")
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentdecompile_recovery.corpus.determinism_harness", description="Run the identity cascade twice from one fixture store and byte-compare identity/match/logical_function.")
    ap.add_argument("store", type=pathlib.Path, help="fixture store (binary/func/calledge rows)")
    ap.add_argument("--seed", type=int, default=FIXTURE_SEED, help="shuffle seed for run B")
    ap.add_argument("--build-fixture", action="store_true", help="first write the synthetic fixture (from --seed) into <store>")
    ap.add_argument("--write-fixture-json", type=pathlib.Path, help="also write the synthetic fixture rows as JSON to this path")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = ap.parse_args(argv)

    if args.build_fixture or args.write_fixture_json:
        snap = generate_fixture(args.seed)
        if args.build_fixture:
            build_fixture_store(args.store, snap)
        if args.write_fixture_json:
            args.write_fixture_json.parent.mkdir(parents=True, exist_ok=True)
            args.write_fixture_json.write_text(dump_fixture_json(snap), encoding="utf-8")
    result = run_harness(args.store, args.seed)
    if args.json:
        print(json.dumps(result.to_json(), indent=1))
    else:
        for label in PERTURBED_RUNS:
            per = result.tables[label]
            for name in OUTPUT_TABLES:
                t = per[name]
                print(f"[{label}] {name}: {'identical' if t.identical else 'DIFFERENT'} ({t.rows_a} vs {t.rows_b} rows)" + (f" -- {t.note}" if t.note else ""))
            t = per["match_no_id"]
            print(f"[{label}] match (ignoring id): {'identical' if t.identical else 'DIFFERENT'}")
        if result.first_diff:
            print(result.first_diff)
        print("RESULT:", "identical" if result.identical else "NOT identical")
    return 0 if result.identical else 1


if __name__ == "__main__":
    sys.exit(main())
