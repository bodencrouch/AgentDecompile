"""logical.build must not depend on func row insertion order."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import logical
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit

FUNC_COLS = (
    "binary_id, addr, name, canon_key, canon_class, canon_method, canon_arity, "
    "name_origin, plate, signature, n_instr, n_blocks, cyclomatic, n_callees, strings, consts"
)

# Two builds; two eligible keys. Within `Widget::run` the plates differ per
# build, so best_signature depends on which member is seen first. Within
# `Widget::tick` build 1 carries two same-name members with equal n_instr so
# the ambiguous path has a rank tie to break.
FUNCS = [
    (1, 0x2000, "run", "Widget::run", "Widget", "run", 1, "plate", "void Widget::run(int)", "void run(int)", 12, 3, 2, 1, "[]", "[]"),
    (2, 0x3000, "run", "Widget::run", "Widget", "run", 1, "plate", "void Widget::run(long)", "void run(long)", 12, 3, 2, 1, "[]", "[]"),
    (1, 0x1000, "tick", "Widget::tick", "Widget", "tick", 0, "plate", "void Widget::tick()", "void tick()", 8, 2, 1, 0, "[]", "[]"),
    (1, 0x1100, "tick", "Widget::tick", "Widget", "tick", 0, "plate", "void Widget::tick()", "void tick()", 8, 2, 1, 0, "[]", "[]"),
    (2, 0x2100, "tick", "Widget::tick", "Widget", "tick", 0, "plate", "void Widget::tick()", "void tick()", 8, 2, 1, 0, "[]", "[]"),
    (2, 0x2200, "tick", "Widget::tick", "Widget", "tick", 0, "plate", "void Widget::tick()", "void tick()", 8, 2, 1, 0, "[]", "[]"),
]


# Content hashes: LOW sorts before HIGH. `_store` gives build 1 the low hash
# so its hash order matches its id/slug order; `_store_hash_reversed` gives
# build 2 the low hash so the two orders disagree and the persisted output
# must follow the hash.
LOW = "1" * 64
HIGH = "f" * 64


def _store(path: Path, funcs, *, hashes: tuple[str | None, str | None] = (LOW, HIGH)):
    con = connect(path)
    con.execute(
        "INSERT INTO binary(id, repo_path, slug, game, content_sha256) VALUES (1, '/a', 'alpha', 'g', ?), (2, '/b', 'beta', 'g', ?)",
        hashes,
    )
    con.executemany(f"INSERT INTO func({FUNC_COLS}) VALUES ({','.join('?' * 16)})", funcs)
    con.commit()
    return con


def _store_hash_reversed(path: Path, funcs):
    return _store(path, funcs, hashes=(HIGH, LOW))


def _dump(con):
    logicals = [tuple(r) for r in con.execute("SELECT * FROM logical_function ORDER BY id")]
    identities = [tuple(r) for r in con.execute("SELECT * FROM identity ORDER BY logical_id, binary_id, addr")]
    return logicals, identities


def test_build_is_insertion_order_independent(tmp_path: Path) -> None:
    forward = _store(tmp_path / "f.sqlite", FUNCS)
    reverse = _store(tmp_path / "r.sqlite", list(reversed(FUNCS)))
    assert logical.build(forward) == logical.build(reverse)
    assert _dump(forward) == _dump(reverse)


def test_best_signature_uses_lowest_member(tmp_path: Path) -> None:
    con = _store(tmp_path / "r.sqlite", list(reversed(FUNCS)))
    logical.build(con)
    row = con.execute("SELECT id, best_signature FROM logical_function WHERE canon_key='Widget::run'").fetchone()
    assert row["id"] == 1
    assert row["best_signature"] == "void Widget::run(int)"


# --- D8: tie-breaks key on binary.content_sha256, never on binary.id --------


def test_best_signature_follows_content_hash_not_rowid(tmp_path: Path) -> None:
    """Same rows, same ids, same slugs; only the hashes swap. The prototype moves with the hash."""
    by_id = _store(tmp_path / "id.sqlite", FUNCS)
    by_hash = _store_hash_reversed(tmp_path / "hash.sqlite", FUNCS)
    logical.build(by_id)
    logical.build(by_hash)
    sig = lambda con: con.execute("SELECT best_signature FROM logical_function WHERE canon_key='Widget::run'").fetchone()[0]
    assert sig(by_id) == "void Widget::run(int)"   # build 1 (alpha) has the low hash
    assert sig(by_hash) == "void Widget::run(long)"  # build 2 (beta) has the low hash


def test_reference_build_in_ambiguous_group_follows_content_hash(tmp_path: Path) -> None:
    """`Widget::tick` ties on member count and role; the 0.97 name-reference slot goes to the lowest hash."""
    by_id = _store(tmp_path / "id.sqlite", FUNCS)
    by_hash = _store_hash_reversed(tmp_path / "hash.sqlite", FUNCS)
    logical.build(by_id)
    logical.build(by_hash)

    def reference_builds(con) -> set[int]:
        return {
            r[0]
            for r in con.execute(
                "SELECT binary_id FROM identity WHERE method='name-reference' AND evidence LIKE '%Widget::tick%'"
            )
        }

    assert reference_builds(by_id) == {1}
    assert reference_builds(by_hash) == {2}


def test_build_is_binary_rowid_order_independent(tmp_path: Path) -> None:
    """Ids and slugs reversed, hashes fixed to the builds: identical output up to the id relabel."""
    con_a = connect(tmp_path / "a.sqlite")
    con_a.execute(
        "INSERT INTO binary(id, repo_path, slug, game, content_sha256) VALUES (1, '/a', 'alpha', 'g', ?), (2, '/b', 'beta', 'g', ?)",
        (LOW, HIGH),
    )
    con_a.executemany(f"INSERT INTO func({FUNC_COLS}) VALUES ({','.join('?' * 16)})", FUNCS)
    con_a.commit()
    # Build "alpha" (hash LOW) is now id 2, "beta" (hash HIGH) is id 1.
    swapped = [(3 - f[0],) + tuple(f[1:]) for f in FUNCS]
    con_b = connect(tmp_path / "b.sqlite")
    con_b.execute(
        "INSERT INTO binary(id, repo_path, slug, game, content_sha256) VALUES (2, '/a', 'alpha', 'g', ?), (1, '/b', 'beta', 'g', ?)",
        (LOW, HIGH),
    )
    con_b.executemany(f"INSERT INTO func({FUNC_COLS}) VALUES ({','.join('?' * 16)})", swapped)
    con_b.commit()
    assert logical.build(con_a) == logical.build(con_b)

    def by_hash(con):
        logicals = [tuple(r) for r in con.execute("SELECT * FROM logical_function ORDER BY id")]
        identities = [
            tuple(r) for r in con.execute(
                "SELECT i.logical_id, b.content_sha256, i.addr, i.confidence, i.method, i.evidence"
                " FROM identity i JOIN binary b ON b.id=i.binary_id ORDER BY 1, 2, 3"
            )
        ]
        return logicals, identities

    assert by_hash(con_a) == by_hash(con_b)


def test_null_content_sha256_refuses_and_names_the_build(tmp_path: Path) -> None:
    con = _store(tmp_path / "n.sqlite", FUNCS, hashes=(LOW, None))
    with pytest.raises(ValueError, match=r"content_sha256.*beta.*backfill --pass content_sha256"):
        logical.build(con)
    blank = _store(tmp_path / "b.sqlite", FUNCS, hashes=("  ", LOW))
    with pytest.raises(ValueError, match=r"alpha"):
        logical.build(blank)


def test_duplicate_content_sha256_refuses(tmp_path: Path) -> None:
    con = _store(tmp_path / "d.sqlite", FUNCS, hashes=(LOW, LOW))
    with pytest.raises(ValueError, match=r"shared by more than one build.*alpha, beta"):
        logical.build(con)


def test_guard_scope_is_the_builds_with_named_functions(tmp_path: Path) -> None:
    """A build with no canon_key rows is out of the cascade's scope and may lack a hash."""
    con = _store(tmp_path / "s.sqlite", FUNCS)
    con.execute("INSERT INTO binary(id, repo_path, slug, game) VALUES (3, '/c', 'gamma', 'g')")
    con.execute("INSERT INTO func(binary_id, addr, name) VALUES (3, 4096, 'FUN_1000')")
    con.commit()
    assert logical.build(con)["logical"] > 0
