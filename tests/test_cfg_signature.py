from agentdecompile_recovery.corpus.cfg_signature import (
    cfg_compatible,
    cfg_shape,
    index_by_md,
    md_index_from_adj,
    md_index_from_counts,
    structural_candidates,
)


def _fn(**fields):
    return dict(fields)


def test_cfg_shape_missing_fields_are_zero():
    assert cfg_shape({}) == (0, 0, 0, 0)
    assert cfg_shape({"n_blocks": 4, "n_edges": None}) == (4, 0, 0, 0)


def test_compatible_vs_incompatible_block_counts():
    small = _fn(n_blocks=5, n_edges=6)
    near = _fn(n_blocks=6, n_edges=7)
    huge = _fn(n_blocks=50, n_edges=70)
    assert cfg_compatible(small, small)
    assert cfg_compatible(small, near)
    assert not cfg_compatible(small, huge)
    assert cfg_compatible(_fn(n_blocks=0, n_edges=0), _fn())


def test_edge_count_slack_is_independent_of_blocks():
    a = _fn(n_blocks=10, n_edges=10)
    close = _fn(n_blocks=10, n_edges=12)
    far = _fn(n_blocks=10, n_edges=20)
    assert cfg_compatible(a, close)
    assert not cfg_compatible(a, far)


def test_identical_counts_share_md_index():
    a = _fn(n_blocks=8, n_edges=11, back_edges=2, cyclomatic=5)
    b = _fn(n_blocks=8, n_edges=11, back_edges=2, cyclomatic=5, name="other")
    c = _fn(n_blocks=8, n_edges=11, back_edges=3, cyclomatic=5)
    assert md_index_from_counts(a) == md_index_from_counts(b)
    assert md_index_from_counts(a) != md_index_from_counts(c)
    assert md_index_from_counts({}) == md_index_from_counts(_fn(n_blocks=0))


def test_isomorphic_dags_share_md_index_rewired_does_not():
    diamond_nodes = ["entry", "left", "right", "exit"]
    diamond_edges = [
        ("entry", "left"),
        ("entry", "right"),
        ("left", "exit"),
        ("right", "exit"),
    ]
    remapped_nodes = [10, 20, 30, 40]
    remapped_edges = [(10, 20), (10, 30), (20, 40), (30, 40)]
    assert md_index_from_adj(diamond_nodes, diamond_edges) == md_index_from_adj(
        remapped_nodes, remapped_edges
    )
    # Same nodes, different wiring (a chain plus a skip), so topology changes.
    rewired = [(10, 20), (20, 30), (30, 40), (10, 40)]
    assert md_index_from_adj(remapped_nodes, rewired) != md_index_from_adj(
        remapped_nodes, remapped_edges
    )
    # Iteration order of nodes/edges must not change the index.
    shuffled_nodes = ["exit", "entry", "right", "left"]
    shuffled_edges = list(reversed(diamond_edges))
    assert md_index_from_adj(shuffled_nodes, shuffled_edges) == md_index_from_adj(
        diamond_nodes, diamond_edges
    )


def test_cycles_do_not_infinite_loop():
    cycle = md_index_from_adj([1, 2, 3], [(1, 2), (2, 3), (3, 1)])
    self_loop = md_index_from_adj(["a"], [("a", "a")])
    mutual = md_index_from_adj([1, 2], [(1, 2), (2, 1)])
    with_isolated = md_index_from_adj([1, 2, 3, 99], [(1, 2), (2, 3), (3, 1)])
    assert isinstance(cycle, int)
    assert isinstance(self_loop, int)
    assert isinstance(mutual, int)
    assert with_isolated != cycle
    assert md_index_from_adj([1, 2, 3], [(1, 2), (2, 3), (3, 1)]) == cycle


def test_structural_candidates_never_returns_huge_dest_for_tiny_src():
    src = _fn(id="src", n_blocks=5, n_edges=6, back_edges=1, cyclomatic=3)
    twin = _fn(id="twin", n_blocks=5, n_edges=6, back_edges=1, cyclomatic=3)
    near = _fn(id="near", n_blocks=6, n_edges=7, back_edges=0, cyclomatic=2)
    huge = _fn(id="huge", n_blocks=50, n_edges=70, back_edges=4, cyclomatic=22)
    hits = structural_candidates(src, [huge, twin, near])
    assert huge not in hits
    assert all(fn["n_blocks"] != 50 for fn in hits)
    assert hits == [twin]

    shape_only = structural_candidates(src, [huge, near])
    assert huge not in shape_only
    assert shape_only == [near]


def test_index_by_md_groups_equal_counts():
    a = _fn(id=1, n_blocks=3, n_edges=2)
    b = _fn(id=2, n_blocks=3, n_edges=2)
    c = _fn(id=3, n_blocks=9, n_edges=12)
    grouped = index_by_md([a, c, b])
    assert grouped[md_index_from_counts(a)] == [a, b]
    assert grouped[md_index_from_counts(c)] == [c]
