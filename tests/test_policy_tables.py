"""``policy_tables.threshold_params``: every live gate, serialized exactly."""

from __future__ import annotations

import inspect
import json
import os

import pytest

from agentdecompile_recovery import symbol_map
from agentdecompile_recovery.corpus import (
    bsim_eval,
    cfg_signature,
    channel_confidence,
    match_engine,
    match_store,
    policy_tables,
)
from agentdecompile_recovery.corpus.export_hookpack import unique_window

pytestmark = pytest.mark.unit


def _reversed(value):
    """Rebuild *value* with every mapping in reverse insertion order."""
    if isinstance(value, dict):
        return {k: _reversed(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [_reversed(v) for v in value]
    return value


def _leaves(value, path="$"):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _leaves(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, value


def test_every_gate_the_cascade_reads_is_represented() -> None:
    t = policy_tables.threshold_params()
    frozen = policy_tables._freeze
    assert t["pair_policy"] == frozen(match_engine.PAIR_POLICY)
    assert t["content_floors"] == {
        "default": repr(match_engine.CONTENT_FLOOR),
        "per_channel": frozen(match_engine.CONTENT_FLOORS),
    }
    assert t["weights"] == frozen(match_engine.WEIGHTS)
    assert t["df_caps"] == {
        "max_const_df": match_engine.MAX_CONST_DF,
        "max_string_df": match_engine.MAX_STRING_DF,
    }
    assert t["channel_confidence"]["base"] == frozen(channel_confidence.BASE)
    assert t["channel_confidence"]["penalties"] == {
        "channel_bonus": channel_confidence.CHANNEL_BONUS,
        "nonunique_penalty": channel_confidence.NONUNIQUE_PENALTY,
        "tight_margin_penalty": channel_confidence.TIGHT_MARGIN_PENALTY,
        "tiny_instr": channel_confidence.TINY_INSTR,
        "tiny_penalty": channel_confidence.TINY_PENALTY,
    }
    assert t["cfg_slack"] == repr(cfg_signature.DEFAULT_SLACK)
    assert t["bsim"] == {
        "margin": repr(policy_tables.BSIM_MARGIN),
        "query_signif": repr(bsim_eval.SIGNIF),
        "query_thresh": repr(bsim_eval.THRESH),
        "tiny_n_instr": policy_tables.BSIM_TINY_N_INSTR,
        "tiny_sim": repr(policy_tables.BSIM_TINY_SIM),
        "trusted_significance": repr(symbol_map.BSIM_TRUSTED_SIGNIFICANCE),
    }
    params = inspect.signature(unique_window).parameters
    assert t["window"] == {"max_n": params["max_n"].default, "min_n": params["min_n"].default}
    assert set(t) == {
        "bsim",
        "cfg_slack",
        "channel_confidence",
        "content_floors",
        "df_caps",
        "pair_policy",
        "weights",
        "window",
    }


def test_pinned_bsim_fusion_literals_still_match_the_source() -> None:
    """The three fusion gates are literals inside ``_fuse_bsim``; keep the pin honest."""
    source = inspect.getsource(match_store._fuse_bsim)
    assert f"(sig - second_sig) < {policy_tables.BSIM_MARGIN!r}" in source
    assert f'("n_instr") or 0) < {policy_tables.BSIM_TINY_N_INSTR}' in source
    assert f"sim >= {policy_tables.BSIM_TINY_SIM!r}" in source
    # The live significance gate is symbol_map's; match_store's 30.0 is only
    # the import-failure fallback and must equal it.
    assert "BSIM_TRUSTED_SIGNIFICANCE = 30.0" in source
    assert symbol_map.BSIM_TRUSTED_SIGNIFICANCE == 30.0


def test_floats_are_repr_strings_and_nothing_else_is_a_float() -> None:
    t = policy_tables.threshold_params()
    for path, leaf in _leaves(t):
        assert not isinstance(leaf, float), path
        assert isinstance(leaf, (int, str)), path
    assert t["pair_policy"]["same_platform"]["auto"] == [
        repr(match_engine.PAIR_POLICY["same_platform"]["auto"][0]),
        repr(match_engine.PAIR_POLICY["same_platform"]["auto"][1]),
        match_engine.PAIR_POLICY["same_platform"]["auto"][2],
    ]
    assert policy_tables._freeze(0.1 + 0.2) == "0.30000000000000004"
    assert policy_tables._freeze(True) is True
    with pytest.raises(TypeError):
        policy_tables._freeze(object())


def test_serialization_is_order_independent_and_sorted() -> None:
    t = policy_tables.threshold_params()
    canonical = json.dumps(t, sort_keys=True, separators=(",", ":"))
    assert json.dumps(_reversed(t), sort_keys=True, separators=(",", ":")) == canonical
    # Keys are already sorted, so sorting is a no-op.
    assert json.dumps(t, separators=(",", ":")) == canonical
    assert policy_tables._freeze({"b": 1, "a": {"d": 2, "c": 3}}) == {"a": {"c": 3, "d": 2}, "b": 1}


def test_accessor_is_pure(monkeypatch) -> None:
    first = policy_tables.threshold_params()
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", "/nowhere")
    monkeypatch.chdir(os.path.dirname(os.path.abspath(__file__)))
    second = policy_tables.threshold_params()
    assert first == second
    assert first is not second
    # A live constant change shows up without a second edit here.
    monkeypatch.setattr(cfg_signature, "DEFAULT_SLACK", 0.5)
    assert policy_tables.threshold_params()["cfg_slack"] == "0.5"
