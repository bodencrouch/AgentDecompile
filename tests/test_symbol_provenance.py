"""Tests for authentic vs heuristic symbol provenance (U11)."""

from agentdecompile_recovery.corpus.symbol_provenance import authentic_named_index, is_authentic_symbol


def test_matcher_inferred_name_is_not_authentic():
    assert not is_authentic_symbol({"name": "Foo", "canon_key": "Foo", "name_origin": "matcher_inferred"})


def test_export_debug_name_is_authentic():
    assert is_authentic_symbol({"name": "ParseSave", "canon_key": "ParseSave", "name_origin": "stabs"})
    assert is_authentic_symbol({"name": "Init", "canon_key": "Init", "source": "IMPORTED", "name_origin": "export"})


def test_authentic_index_excludes_inferred():
    funcs = {
        1: {"canon_key": "A", "name": "A", "name_origin": "matcher_inferred"},
        2: {"canon_key": "B", "name": "B", "name_origin": "stabs"},
    }
    idx = authentic_named_index(funcs)
    assert "A" not in idx
    assert idx["B"] == [2]
