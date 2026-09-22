"""agentdecompile_grid.view -- materialized views replayed from the verified stream.

Importing this package registers the appliers in ``core.APPLIERS``: ``sqlite`` (working) and
``similarity`` (declared).  Kind-specific hooks are registered by lane modules through
``view_hook``; the grid never imports the recovery package.
"""
from __future__ import annotations

from .applier import (  # noqa: F401
    SQLiteViewApplier,
    VIEW_HOOKS,
    VIEW_RESETS,
    ViewBasisMismatch,
    ViewGap,
    ViewHookFailed,
    ViewStale,
    materialize,
    open_view,
    view_hook,
    view_reset,
)
from .similarity import SimilarityIndexApplier  # noqa: F401

__all__ = [
    "SQLiteViewApplier", "SimilarityIndexApplier", "VIEW_HOOKS", "VIEW_RESETS",
    "ViewBasisMismatch", "ViewGap", "ViewHookFailed", "ViewStale",
    "materialize", "open_view", "view_hook", "view_reset",
]
