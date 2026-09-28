from agentdecompile_recovery.corpus.block_inline import (
    block_hash_set,
    blocks_contained,
    inline_hits,
    likely_inlined,
)


def _fn(fid, *, hashes=None, blocks=None, use_addr_only=False):
    row = {"addr": fid} if use_addr_only else {"id": fid, "addr": fid}
    if hashes is not None:
        row["block_hashes"] = hashes
    if blocks is not None:
        row["blocks"] = blocks
    return row


def test_subset_of_hashes_inlines_to_unique_host():
    missing = [_fn("helper", hashes=["b1", "b2"])]
    survivors = [
        _fn("host", hashes=["b1", "b2", "b3", "b4"]),
        _fn("other", hashes=["x1", "x2"]),
    ]
    assert blocks_contained(missing[0], survivors[0])
    assert not blocks_contained(missing[0], survivors[1])
    hits = inline_hits(missing, survivors)
    assert hits == [
        {
            "missing_id": "helper",
            "host_id": "host",
            "kind": "inline",
            "block_count": 2,
        }
    ]
    assert likely_inlined(missing, survivors) == hits


def test_hashes_split_across_two_hosts_no_hit():
    missing = [_fn("helper", hashes=["left", "right"])]
    survivors = [
        _fn("a", hashes=["left", "other"]),
        _fn("b", hashes=["right", "other"]),
    ]
    assert inline_hits(missing, survivors) == []


def test_empty_hashes_no_hit():
    missing = [
        _fn("no_field"),
        _fn("empty_list", hashes=[]),
        _fn("empty_blocks", blocks=[]),
    ]
    survivors = [_fn("host", hashes=["b1", "b2"])]
    assert all(block_hash_set(fn) == frozenset() for fn in missing)
    assert inline_hits(missing, survivors) == []
    assert inline_hits([_fn("helper", hashes=["b1"])], [_fn("bare")]) == []


def test_unique_containment_among_several_survivors():
    missing = [_fn("0x100", hashes=["h1", "h2"], use_addr_only=True)]
    survivors = [
        _fn("too_small", hashes=["h1"]),
        _fn("unrelated", hashes=["z1", "z2", "z3"]),
        _fn("the_host", hashes=["h1", "h2", "h3"]),
        _fn("also_unrelated", hashes=["q1"]),
    ]
    hits = inline_hits(missing, survivors)
    assert hits == [
        {
            "missing_id": "0x100",
            "host_id": "the_host",
            "kind": "inline",
            "block_count": 2,
        }
    ]


def test_contained_in_two_survivors_is_ambiguous():
    missing = [_fn("helper", blocks=[{"hash": "aa"}, {"hash": "bb"}])]
    survivors = [
        _fn("one", hashes=["aa", "bb", "cc"]),
        _fn("two", hashes=["aa", "bb", "dd"]),
    ]
    assert block_hash_set(missing[0]) == frozenset({"aa", "bb"})
    assert inline_hits(missing, survivors) == []
