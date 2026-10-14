"""Explicit terminal outcome for every source function of a pair match (U1 RC-10, D24).

A pair match used to report only accepted rows, so an unmatched function had no stated
reason. Each in-scope source function now ends in exactly one outcome:

- ``matched``: bound by an accepted identity row.
- ``inlined``: block-level inline/fold/split evidence, never an identity claim.
- ``ambiguous``: candidates were scored but none cleared policy, or several tied.
- ``unsupported``: the matcher does not attempt this function (thunk, too few instructions).
- ``budget_limited``: the round budget ran out while rounds were still adding matches.
- ``absent``: no candidate under this search.

Only ``matched`` is a positive claim. No outcome asserts that a counterpart does not exist:
``exhaustive`` is always false, and a genuine negative needs independent evidence.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

OUTCOMES = ("matched", "inlined", "ambiguous", "unsupported", "budget_limited", "absent")
NON_IDENTITY_KINDS = frozenset({"inline", "fold", "split", "clone", "unroll"})  # block_inline relations
MIN_INSTR = 4


def _unsupported_reason(fn: Mapping[str, Any]) -> str | None:
    if fn.get("is_thunk"):
        return "thunk"
    if (fn.get("n_instr") or 0) < MIN_INSTR:
        return "too_few_instructions"
    return None


def terminal_outcomes(
    src_funcs: Mapping[int, Mapping[str, Any]],
    mapping: Mapping[int, int],
    results: Mapping[int, Mapping[str, Any]],
    *,
    scope: Iterable[int] | None = None,
    budget_limited: bool = False,
) -> dict[str, Any]:
    """Return ``{"rows": {addr: outcome-row}, "counts": {...}, "exhaustive": False}``."""
    rows: dict[int, dict[str, Any]] = {}
    for addr in sorted(scope if scope is not None else src_funcs):
        fn = src_funcs.get(addr) or {}
        result = results.get(addr) or {}
        kind = str(result.get("kind") or "")
        unsupported = _unsupported_reason(fn)
        if addr in mapping:
            row = {"outcome": "matched", "dst": mapping[addr], "kind": kind or "identity"}
        elif unsupported:
            row = {"outcome": "unsupported", "reason": unsupported}
        elif kind in NON_IDENTITY_KINDS:
            row = {"outcome": "inlined", "host": result.get("dst"), "relation": kind}
        elif result:
            tied = kind == "ambiguous" or result.get("ambiguity")
            row = {"outcome": "ambiguous", "reason": "tied_candidates" if tied else "candidates_below_policy",
                   "best": result.get("dst"), "score": result.get("score")}
        elif budget_limited:
            row = {"outcome": "budget_limited", "reason": "round_budget_exhausted_while_still_matching"}
        else:
            row = {"outcome": "absent", "reason": "no_candidate_under_this_search"}
        rows[addr] = row
    counts = Counter(row["outcome"] for row in rows.values())
    return {"rows": rows, "counts": {name: counts.get(name, 0) for name in OUTCOMES},
            "exhaustive": False,
            "note": "Only 'matched' is a positive claim; no outcome asserts that a counterpart does not exist."}
