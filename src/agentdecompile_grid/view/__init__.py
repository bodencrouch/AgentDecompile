"""agentdecompile_grid.view -- materialized views replayed from the verified stream.

Importing this package registers the appliers in ``core.APPLIERS``: ``sqlite`` (working) and
``similarity`` (declared).  Kind-specific hooks are registered by lane modules through
``view_hook``; the table-aware delta binders (``identity-delta``, ``logical-delta``,
``image-registered``, ``basis-stamped``) through ``delta_binder``; the grid never imports the
recovery package.  ``deltas`` holds the generic delta object schema (``agentdecompile.delta.v1``).
"""
from __future__ import annotations

from .applier import (  # noqa: F401
    CONFLICT_POLICIES,
    DELTA_BINDERS,
    BindReceipt,
    BinderRefused,
    ConflictPolicy,
    DeltaBinder,
    RefuseOnConflict,
    SQLiteViewApplier,
    VIEW_HOOKS,
    VIEW_RESETS,
    ViewBasisMismatch,
    ViewGap,
    ViewHookFailed,
    ViewStale,
    delta_binder,
    materialize,
    open_view,
    view_hook,
    view_reset,
)
from .deltas import Delta, delta_ref, load_delta, put_delta, validate_delta  # noqa: F401
from .similarity import SimilarityIndexApplier  # noqa: F401

__all__ = [
    "BindReceipt", "BinderRefused", "CONFLICT_POLICIES", "ConflictPolicy", "DELTA_BINDERS", "Delta", "DeltaBinder",
    "RefuseOnConflict", "SQLiteViewApplier", "SimilarityIndexApplier", "VIEW_HOOKS", "VIEW_RESETS",
    "ViewBasisMismatch", "ViewGap", "ViewHookFailed", "ViewStale", "delta_binder", "delta_ref", "load_delta",
    "materialize", "open_view", "put_delta", "validate_delta", "view_hook", "view_reset",
]
