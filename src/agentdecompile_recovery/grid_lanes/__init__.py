"""agentdecompile_recovery.grid_lanes -- the pipeline's task kinds as grid adapters.

Import direction is **recovery -> grid only**: this package imports ``agentdecompile_grid`` and
registers into its registries; nothing under ``agentdecompile_grid`` names this package.  The
grid CLI reaches these lanes by module name from its config (``lanes``), the ``ADGRID_LANES``
environment variable or the ``agentdecompile_grid.lanes`` entry-point group -- never by a
literal import (U120's boundary test).

Importing this package registers, in ``agentdecompile_grid.core.TASK_KINDS``:

* working kinds -- ``corpus-export-hookpack``, ``corpus-backfill-pass``,
  ``corpus-verify-determinism``, ``corpus-logical-build``, ``compile-attempt``, ``parity-check``,
  ``mkobj-target``, ``match-score-shard``;
* declared kinds -- ``corpus-attest`` (U168 over U28x's ``corpus attest``), ``analysis-slice``,
  ``decompile-chunk``, ``bsim-sigs`` (U137/U139/U141);

plus one planner per kind in ``splitter.PLANNERS`` (reached by ``Kind.plan``) and one view hook
per materialized kind in ``agentdecompile_grid.view.applier.VIEW_HOOKS`` (receipt tables only; the
applier never writes identity tables and neither do these hooks -- U143/U150 bind deltas).

Basis rule (U158/U158b): a lane declares one basis field set; the projection, not the full hash,
keys its tasks.  ``_common.BASIS_FIELD_SETS`` names the sets (``content_only``, ``analyzer``,
``toolchain``, ``cascade``, ``corpus_verb``, ``parity``); a kind names one in ``basis_field_set``
and ``PlannableKind`` derives ``basis_fields`` from it, so ``adgrid describe`` lists no lane under
``basis_projections.undeclared``.  Planners (U158c) project those fields from a ``BasisSource``
(``_common.StoreBasisSource`` reads the snapshot's ``determinism_basis.basis``; the repair source
uses package policy for intentionally incomplete stores) through ``_common.lane_spec``. The pack
source remains unavailable and is not advertised by a planner.

``describe_lanes()`` returns every kind's ``describe()`` plus the planner catalogue and, under
``basis``, each kind's set name and derived fields.

Acceptance tests (named): ``test_grid_lanes_import_registers_kinds``,
``test_grid_never_imports_recovery`` (grep ``agentdecompile_recovery`` under
``src/agentdecompile_grid`` is empty), ``test_every_kind_describes_itself``.
"""
from __future__ import annotations

from typing import Any

from agentdecompile_grid.core import TASK_KINDS

from ._common import (
    BASIS_FIELD_SETS, BASIS_SOURCES, BasisRefused, BasisSource, ContentHashRefused, ExplicitBasisSource, Infra, Locked,
    PackBasisSource, PlannableKind, RepairBasisSource, ResolvedBasis, StoreBasisSource, basis_fields_for, hashed_slug,
    lane_spec, project_for,
)
from . import analysis, cascade, compile, parity, parity_region, splitter, target, verbs  # noqa: F401  (registration on import)

LANE_KINDS: tuple[type, ...] = (
    *verbs.VERB_KINDS, compile.CompileAttempt, parity.ParityCheck, parity_region.ParityRegionCheck, target.MkobjTarget,
    cascade.MatchScoreShard, *analysis.ANALYSIS_KINDS,
)


def describe_lanes() -> dict[str, Any]:
    """Every lane kind's ``describe()`` (working and declared), each kind's basis field set and
    derived fields, the named sets themselves, and the planner catalogue."""
    return {
        "kinds": {cls.name: cls.describe() for cls in LANE_KINDS},
        "registered": [name for name in TASK_KINDS.names() if any(name == cls.name for cls in LANE_KINDS)],
        "basis": {cls.name: cls.describe_basis() for cls in LANE_KINDS},
        "basis_field_sets": {name: list(fields) for name, fields in BASIS_FIELD_SETS.items()},
        "planners": splitter.describe_planners(),
        "errors": {
            cls.__name__: cls.exit_code for cls in (BasisRefused, ContentHashRefused, Locked, Infra)
        },
    }


__all__ = [
    "BASIS_FIELD_SETS", "BASIS_SOURCES", "BasisRefused", "BasisSource", "ContentHashRefused",
    "ExplicitBasisSource", "Infra", "LANE_KINDS", "Locked", "PackBasisSource", "PlannableKind",
    "RepairBasisSource", "ResolvedBasis", "StoreBasisSource", "analysis", "basis_fields_for", "cascade", "compile",
    "describe_lanes", "hashed_slug", "lane_spec", "parity", "project_for", "splitter", "target", "verbs",
]
