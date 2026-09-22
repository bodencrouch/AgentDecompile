"""agentdecompile_recovery.grid_lanes -- the pipeline's task kinds as grid adapters.

Import direction is **recovery -> grid only**: this package imports ``agentdecompile_grid`` and
registers into its registries; nothing under ``agentdecompile_grid`` names this package.  The
grid CLI reaches these lanes by module name from its config (``lanes``), the ``ADGRID_LANES``
environment variable or the ``agentdecompile_grid.lanes`` entry-point group -- never by a
literal import (U120's boundary test).

Importing this package registers, in ``agentdecompile_grid.core.TASK_KINDS``:

* working kinds -- ``corpus-export-hookpack``, ``corpus-backfill-pass``,
  ``corpus-verify-determinism``, ``corpus-logical-build``, ``corpus-attest`` (``verbs``; U168 over
  U28x's ``corpus attest``), ``compile-attempt`` (``compile``), ``parity-check`` (``parity``),
  ``match-score-shard`` (``cascade``);
* declared kinds -- ``analysis-slice``, ``decompile-chunk``, ``bsim-sigs`` (``analysis``;
  U137/U139/U141);

plus one planner per kind in ``splitter.PLANNERS`` (reached by ``Kind.plan``) and one view hook
per working kind in ``agentdecompile_grid.view.applier.VIEW_HOOKS`` (receipt tables only; the
applier never writes identity tables and neither do these hooks -- U143/U150 bind deltas).

``describe_lanes()`` returns every kind's ``describe()`` plus the planner catalogue.

Acceptance tests (named): ``test_grid_lanes_import_registers_kinds``,
``test_grid_never_imports_recovery`` (grep ``agentdecompile_recovery`` under
``src/agentdecompile_grid`` is empty), ``test_every_kind_describes_itself``.
"""
from __future__ import annotations

from typing import Any

from agentdecompile_grid.core import TASK_KINDS

from . import analysis, cascade, compile, parity, splitter, verbs  # noqa: F401  (registration on import)
from ._common import BasisRefused, ContentHashRefused, Infra, Locked, PlannableKind, hashed_slug

LANE_KINDS: tuple[type, ...] = (
    *verbs.VERB_KINDS, compile.CompileAttempt, parity.ParityCheck, cascade.MatchScoreShard, *analysis.ANALYSIS_KINDS,
)


def describe_lanes() -> dict[str, Any]:
    """Every lane kind's ``describe()`` (working and declared) plus the planner catalogue."""
    return {
        "kinds": {cls.name: cls.describe() for cls in LANE_KINDS},
        "registered": [name for name in TASK_KINDS.names() if any(name == cls.name for cls in LANE_KINDS)],
        "planners": splitter.describe_planners(),
        "errors": {
            cls.__name__: cls.exit_code for cls in (BasisRefused, ContentHashRefused, Locked, Infra)
        },
    }


__all__ = [
    "BasisRefused", "ContentHashRefused", "Infra", "LANE_KINDS", "Locked", "PlannableKind", "analysis", "cascade",
    "compile", "describe_lanes", "hashed_slug", "parity", "splitter", "verbs",
]
