"""Cascade determinism gate (plan U5c b / U28 e).

Runs the identity cascade from one synthetic fixture under three physical
layouts and byte-compares ``identity``, ``match`` and ``logical_function``.
The fixture deliberately contains fingerprint ties, duplicate names within a
build, contested callgraph destinations and equal-score fuzzy sources, so a
first-wins decision anywhere in the cascade shows up as a table diff.
"""

from __future__ import annotations

import collections
import json
import pathlib

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


def test_cascade_is_order_and_layout_independent(tmp_path: pathlib.Path) -> None:
    fixture_store = harness.build_fixture_store(tmp_path / "fixture.sqlite", _fixture_rows())
    result = harness.run_harness(fixture_store, seed=harness.FIXTURE_SEED, work_dir=tmp_path)

    # Guard against a vacuous pass: every output table must be populated and
    # the cascade must have reached the bind stage in the canonical run.
    con = store.connect(tmp_path / "fixture.canonical.sqlite")
    try:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in harness.OUTPUT_TABLES}
        methods = {r[0] for r in con.execute("SELECT method FROM identity")}
    finally:
        con.close()
    assert all(counts[t] > 0 for t in harness.OUTPUT_TABLES), counts
    assert any(m.startswith(f"match:{harness.RUN}:") for m in methods), methods

    identical = result.identical
    assert identical, result.first_diff
