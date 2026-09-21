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


def _store(path: Path, funcs):
    con = connect(path)
    con.execute("INSERT INTO binary(id, repo_path, slug, game) VALUES (1, '/a', 'alpha', 'g'), (2, '/b', 'beta', 'g')")
    con.executemany(f"INSERT INTO func({FUNC_COLS}) VALUES ({','.join('?' * 16)})", funcs)
    con.commit()
    return con


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
