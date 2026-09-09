"""ABI discriminator tests (U4)."""

from agentdecompile_recovery.corpus.match_engine import abi_compatibility, score_features, status_for


def test_compatible_arity_boosts_but_alone_not_identity():
    fa = {"strings": [], "consts": [], "ext_calls": [], "canon_arity": 2, "calling_convention": "cdecl"}
    fb = {"strings": [], "consts": [], "ext_calls": [], "canon_arity": 2, "calling_convention": "cdecl"}
    score, ev = score_features(fa, fb)
    assert ev.get("abi") == 1.0
    # ABI/arity alone can score high but must not auto-bind without content channels.
    assert status_for(score, 1.0, "same_platform", content=0) != "auto"


def test_incompatible_arity_zeros_score():
    fa = {"strings": ["rare_unique_string_xyz"], "consts": [0x12345], "ext_calls": [], "canon_arity": 1}
    fb = {"strings": ["rare_unique_string_xyz"], "consts": [0x12345], "ext_calls": [], "canon_arity": 4}
    score, ev = score_features(fa, fb)
    assert ev.get("abi") == 0.0
    assert score == 0.0


def test_abi_none_when_missing():
    assert abi_compatibility({}, {}) is None
