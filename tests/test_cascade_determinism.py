"""Cascade determinism gate (plan U5c b / U28 e).

Runs the identity cascade from one synthetic fixture under three physical
layouts (canonical; shuffled rows with fresh ``binary`` ids; the same plus
``VACUUM; ANALYZE``) and byte-compares ``identity``, ``match`` (including
``id``), ``logical_function`` and ``binary.recovery_family`` as sorted
canonical row-sets keyed on ``content_sha256``. The fixture deliberately
contains fingerprint ties, duplicate names within a build, contested callgraph
destinations, equal-score fuzzy sources and one logical function claiming an
unnamed destination from two builds, so a first-wins decision anywhere in the
cascade — including one keyed on ``binary.id`` — shows up as a table diff.
"""

from __future__ import annotations

import collections
import json
import pathlib
import random

import pytest

from agentdecompile_recovery.corpus import determinism_harness as harness
from agentdecompile_recovery.corpus import store

pytestmark = pytest.mark.determinism_cascade

FIXTURE_JSON = pathlib.Path(__file__).parent / "fixtures" / "determinism" / harness.FIXTURE_JSON_NAME


def _fixture_rows() -> dict[str, list[dict]]:
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


def test_fixture_json_matches_seeded_generation() -> None:
    """The committed fixture is exactly what ``generate_fixture(FIXTURE_SEED)`` emits."""
    assert harness.dump_fixture_json(harness.generate_fixture(harness.FIXTURE_SEED)) == FIXTURE_JSON.read_text(encoding="utf-8")


def test_fixture_exercises_order_dependent_paths() -> None:
    rows = _fixture_rows()
    builds = {b["id"] for b in rows["binary"]}
    assert len(builds) >= 3
    per_build: dict[int, list[dict]] = collections.defaultdict(list)
    for f in rows["func"]:
        per_build[f["binary_id"]].append(f)
    for bid in builds:
        funcs = per_build[bid]
        assert len(funcs) >= 30
        # Same authentic name at two addresses in one build -> resolve_ambiguous ties.
        keys = collections.Counter(f["canon_key"] for f in funcs if f.get("canon_key"))
        assert any(n >= 2 for n in keys.values())
        # Fingerprint collisions inside a build -> no unique hash anchor.
        reloc = collections.Counter(f["hash_reloc"] for f in funcs)
        assert any(n >= 2 for n in reloc.values())
        assert all(int(f.get("n_instr") or 0) >= 8 and not f.get("is_thunk") for f in funcs)
    # Contested destinations: distinct authentic names in two builds, unnamed in the third.
    names = {f["canon_key"] for f in rows["func"] if f.get("canon_key")}
    assert {"Gamma0::left", "Gamma0::right"} <= names
    assert rows["calledge"]
    # No product, binary or project names: every slug/path is synthetic.
    assert all(b["slug"].startswith("build-") and b["repo_path"].startswith("/fixture/") for b in rows["binary"])


def _hash_order(rows: dict[str, list[dict]]) -> list[str]:
    return [b["slug"] for b in sorted(rows["binary"], key=lambda b: b["content_sha256"])]


def _fresh_id_order(rows: dict[str, list[dict]], seed: int, path: pathlib.Path) -> list[str]:
    """Slugs in the order of the fresh ``binary.id`` a shuffled load assigns."""
    con = harness._fresh(path)
    try:
        id_map = harness.load_snapshot(con, rows, rng=random.Random(seed))
        slug_of = {b["id"]: b["slug"] for b in rows["binary"]}
        return [slug_of[old] for old, _new in sorted(id_map.items(), key=lambda kv: kv[1])]
    finally:
        con.close()


def test_shuffled_load_assigns_fresh_binary_ids_and_remaps_foreign_keys(tmp_path: pathlib.Path) -> None:
    rows = _fixture_rows()
    con = harness._fresh(tmp_path / "shuffled.sqlite")
    try:
        id_map = harness.load_snapshot(con, rows, rng=random.Random(harness.FIXTURE_SEED))
        assert sorted(id_map) == sorted(b["id"] for b in rows["binary"])
        assert id_map != {i: i for i in id_map}, "the shuffle must move at least one binary.id"
        # Every FK follows its build: per-build func/calledge counts are unchanged under the map.
        for table in ("func", "calledge"):
            want = collections.Counter(id_map[r["binary_id"]] for r in rows[table])
            got = collections.Counter(r[0] for r in con.execute(f"SELECT binary_id FROM {table}"))
            assert got == want, table
        assert con.execute("SELECT COUNT(*) FROM func f LEFT JOIN binary b ON b.id=f.binary_id WHERE b.id IS NULL").fetchone()[0] == 0
    finally:
        con.close()


def test_shuffle_seeds_perturb_every_build_order(tmp_path: pathlib.Path) -> None:
    """The gate is vacuous if fresh ids follow content-hash order; one seed must reverse it."""
    rows = _fixture_rows()
    by_hash = _hash_order(rows)
    orders = {seed: _fresh_id_order(rows, seed, tmp_path / f"seed{seed}.sqlite") for seed in harness.SHUFFLE_SEEDS}
    assert all(order != by_hash for order in orders.values()), orders
    assert list(reversed(by_hash)) in orders.values(), orders


def test_missing_fixture_table_is_an_error(tmp_path: pathlib.Path) -> None:
    rows = _fixture_rows()
    rows.pop("calledge")
    con = harness._fresh(tmp_path / "partial.sqlite")
    try:
        with pytest.raises(ValueError, match="missing table"):
            harness.load_snapshot(con, rows)
    finally:
        con.close()


@pytest.mark.parametrize("seed", harness.SHUFFLE_SEEDS)
def test_cascade_is_order_and_layout_independent(tmp_path: pathlib.Path, seed: int) -> None:
    fixture_store = harness.build_fixture_store(tmp_path / "fixture.sqlite", _fixture_rows())
    result = harness.run_harness(fixture_store, seed=seed, work_dir=tmp_path)

    # Guard against a vacuous pass: every output table must be populated and
    # the cascade must have reached the bind stage in the canonical run.
    con = store.connect(tmp_path / "fixture.canonical.sqlite")
    try:
        counts = {
            t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in harness.OUTPUT_TABLES
            if t != "recovery_family"
        }
        counts["recovery_family"] = con.execute(
            "SELECT COUNT(*) FROM binary WHERE recovery_family IS NOT NULL AND trim(recovery_family)<>''"
        ).fetchone()[0]
        methods = {r[0] for r in con.execute("SELECT method FROM identity")}
    finally:
        con.close()
    assert all(counts[t] > 0 for t in harness.OUTPUT_TABLES), counts
    assert any(m.startswith(f"match:{harness.RUN}:") for m in methods), methods

    identical = result.identical
    assert identical, result.first_diff
    for label in harness.PERTURBED_RUNS:
        assert result.tables[label]["match"].identical, (label, result.tables[label]["match"].first_diff)
        assert result.tables[label]["recovery_family"].rows_a == len(_fixture_rows()["binary"])
