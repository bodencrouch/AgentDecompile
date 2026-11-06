"""agentdecompile_grid.tasks — task kinds, canonical specs, budgets, results.

Importing this package registers the three builtin kinds (``hash-object``, ``python-canary``,
``subprocess-verb``) in ``core.TASK_KINDS`` and records their source as ``builtin``.  Entry-point
kinds (group ``agentdecompile_grid.task_kinds``) are discovered lazily by ``registry.ensure_discovered``
or ``describe_kinds``; the grid never imports the recovery pipeline.

Public surface (re-exported):

* ``spec``: ``build_spec``, ``spec_for_kind``, ``validate_spec``, ``normalize_params``, ``param_*``,
  ``write_spec``/``read_spec``, ``SpecError``.
* ``registry``: ``register_kind``, ``get_kind``, ``execute``, ``describe_kinds``, ``discover_entry_points``.
* ``budget``: ``deadline_for``, ``deadline_for_spec``, ``check_offerable``, ``timeout_policy``, ``BudgetClock``.
* ``results``: ``write_result``/``read_result``, ``write_verification``/``read_verification``,
  ``proposal_count``, ``result_refs``, ``verified_result_ref``, ``is_done``, ``ProposalCapExceeded``, ``PROPOSAL_CAP``.
* ``builtin``: the three kinds and ``PythonCanary``.
"""
from __future__ import annotations

from . import budget, builtin, registry, results, spec
from .budget import BudgetClock, Deadline, check_offerable, deadline_for, deadline_for_spec, timeout_policy, timeout_policy_hash
from .builtin import BUILTIN_KINDS, HashObjectKind, PythonCanary, PythonCanaryKind, SubprocessVerbKind
from .registry import (
    KindError, describe_kinds, discover_entry_points, ensure_discovered, execute, get_kind, kind_names, register_kind,
)
from .results import (
    PROPOSAL_CAP, ProposalCapExceeded, is_done, proposal_count, read_result, read_verification, result_refs, results_for,
    verified_result_ref, verifications_for, write_result, write_verification,
)
from .spec import SpecError, build_spec, normalize_params, read_spec, spec_for_kind, validate_spec, write_spec

for _kind in BUILTIN_KINDS:
    registry._SOURCES.setdefault(_kind.name, "builtin")


def describe(config: object = None) -> dict:
    """What ``adgrid tasks describe`` prints: kinds, budgets, proposal cap."""
    out: dict = {"kinds": describe_kinds(config)["kinds"], "proposal_cap": PROPOSAL_CAP}
    if config is not None:
        out["budgets"] = budget.describe_budgets(config)
        out["proposal_cap"] = config.tasks.proposal_cap  # type: ignore[attr-defined]
    return out


__all__ = [
    "budget", "builtin", "registry", "results", "spec", "describe",
    "BudgetClock", "Deadline", "check_offerable", "deadline_for", "deadline_for_spec", "timeout_policy", "timeout_policy_hash",
    "BUILTIN_KINDS", "HashObjectKind", "PythonCanary", "PythonCanaryKind", "SubprocessVerbKind",
    "KindError", "describe_kinds", "discover_entry_points", "ensure_discovered", "execute", "get_kind", "kind_names", "register_kind",
    "PROPOSAL_CAP", "ProposalCapExceeded", "is_done", "proposal_count", "read_result", "read_verification", "result_refs",
    "results_for", "verified_result_ref", "verifications_for", "write_result", "write_verification",
    "SpecError", "build_spec", "normalize_params", "read_spec", "spec_for_kind", "validate_spec", "write_spec",
]
