"""Serialize the live threshold tables the identity cascade reads.

One read-only accessor, :func:`threshold_params`, builds a nested dict from
the constants the owning modules define. Nothing here is a copy of a value
that can be imported: every number is read from the module that owns it at
call time, so a threshold change shows up in the basis without a second
edit. The three BSim fusion gates are the exception: ``match_store._fuse_bsim``
holds them as literals, so they are pinned here and a test checks the
literals still appear in that function's source.

Rules the accessor keeps:

* Pure. No I/O, no environment, no clock. Two calls return equal objects.
* Floats are serialized as ``repr`` strings so the value in a pack is the
  exact Python float, whatever JSON writer or reader sits in between.
* Every mapping is built with sorted keys; tuples become lists.
"""

from __future__ import annotations

import inspect
from typing import Any

# Literals inside match_store._fuse_bsim. Pinned, not imported: the function
# body owns them. test_policy_tables checks the source still carries them.
BSIM_MARGIN = 5.0
BSIM_TINY_N_INSTR = 8
BSIM_TINY_SIM = 0.99


def _freeze(value: Any) -> Any:
    """Recursively normalise *value* into sorted dicts, lists and repr floats."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {str(k): _freeze(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_freeze(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_freeze(v) for v in value)
    raise TypeError(f"threshold_params cannot serialize {type(value).__name__}")


def threshold_params() -> dict:
    """The live policy tables as one sorted, JSON-ready dict.

    Keys are stable; a new gate is a new key, never a changed one. Callers
    treat an empty result as a gate failure.
    """
    from . import bsim_eval, cfg_signature, channel_confidence, match_engine
    from .export_hookpack import unique_window
    from .. import symbol_map

    window_params = inspect.signature(unique_window).parameters
    return _freeze(
        {
            "pair_policy": match_engine.PAIR_POLICY,
            "content_floors": {
                "default": match_engine.CONTENT_FLOOR,
                "per_channel": match_engine.CONTENT_FLOORS,
            },
            "weights": match_engine.WEIGHTS,
            "df_caps": {
                "max_string_df": match_engine.MAX_STRING_DF,
                "max_const_df": match_engine.MAX_CONST_DF,
            },
            "channel_confidence": {
                "base": channel_confidence.BASE,
                "penalties": {
                    "tiny_instr": channel_confidence.TINY_INSTR,
                    "tiny_penalty": channel_confidence.TINY_PENALTY,
                    "nonunique_penalty": channel_confidence.NONUNIQUE_PENALTY,
                    "tight_margin_penalty": channel_confidence.TIGHT_MARGIN_PENALTY,
                    "channel_bonus": channel_confidence.CHANNEL_BONUS,
                },
            },
            "cfg_slack": cfg_signature.DEFAULT_SLACK,
            "bsim": {
                "trusted_significance": symbol_map.BSIM_TRUSTED_SIGNIFICANCE,
                "margin": BSIM_MARGIN,
                "tiny_n_instr": BSIM_TINY_N_INSTR,
                "tiny_sim": BSIM_TINY_SIM,
                "query_thresh": bsim_eval.THRESH,
                "query_signif": bsim_eval.SIGNIF,
            },
            "window": {
                "min_n": window_params["min_n"].default,
                "max_n": window_params["max_n"].default,
            },
        }
    )
