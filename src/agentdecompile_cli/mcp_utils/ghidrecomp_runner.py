"""Run ``ghidrecomp.decompile`` and close every decompiler it opened.

ghidrecomp 0.5.x ``decompile()`` builds ``thread_count`` ``DecompInterface``
objects through ``setup_decompliers`` (sic) and never disposes them. Each call
therefore leaves that many native ``decompile`` processes alive for the life of
the JVM. In a long-lived server a handful of batch calls reached 64 of them.

``run_ghidrecomp`` records every pool built during one call and disposes it
afterwards, whether the call returns or raises.
"""

from __future__ import annotations

import contextvars
import importlib
import logging
import threading
from types import ModuleType
from typing import Any, Callable

logger = logging.getLogger(__name__)

_GHIDRECOMP_MODULE = "ghidrecomp.decompile"
_PATCH_MARK = "_agentdecompile_tracks_pools"
_install_lock = threading.Lock()
_active_pools: contextvars.ContextVar[list[Any] | None] = contextvars.ContextVar(
    "ghidrecomp_decompiler_pools",
    default=None,
)


def _tracking(original: Callable[..., Any]) -> Callable[..., Any]:
    def setup_decompliers(*args: Any, **kwargs: Any) -> Any:
        pool = original(*args, **kwargs)
        pools = _active_pools.get()
        if pools is not None:
            pools.append(pool)
        return pool

    setattr(setup_decompliers, _PATCH_MARK, True)
    setup_decompliers.__wrapped__ = original  # type: ignore[attr-defined]
    return setup_decompliers


def install_decompiler_tracking(module: ModuleType | None = None) -> bool:
    """Wrap ``ghidrecomp.decompile.setup_decompliers`` once (idempotent).

    ``decompile()`` looks the function up in its own module globals, so
    replacing the module attribute covers every caller of ``decompile``.
    """
    mod = module
    if mod is None:
        try:
            mod = importlib.import_module(_GHIDRECOMP_MODULE)
        except ImportError:
            return False
    with _install_lock:
        current = getattr(mod, "setup_decompliers", None)
        if current is None:
            return False
        if not getattr(current, _PATCH_MARK, False):
            mod.setup_decompliers = _tracking(current)
    return True


def dispose_decompiler_pool(pool: Any) -> int:
    """Dispose each decompiler in ``pool`` (dict or iterable); return how many closed."""
    if pool is None:
        return 0
    decompilers = list(pool.values()) if isinstance(pool, dict) else list(pool)
    disposed = 0
    for decomp in decompilers:
        try:
            decomp.dispose()
            disposed += 1
        except Exception as exc:  # one bad decompiler must not strand the rest
            logger.warning("ghidrecomp_decompiler_dispose_failed exc_type=%s msg=%s", type(exc).__name__, exc)
    return disposed


def run_ghidrecomp(args: Any, runner: Callable[[Any], Any] | None = None) -> Any:
    """Call ``runner(args)`` (default ``ghidrecomp.decompile.decompile``) and dispose its decompilers."""
    if runner is None:
        runner = importlib.import_module(_GHIDRECOMP_MODULE).decompile
    install_decompiler_tracking()
    pools: list[Any] = []
    token = _active_pools.set(pools)
    try:
        return runner(args)
    finally:
        _active_pools.reset(token)
        disposed = sum(dispose_decompiler_pool(pool) for pool in pools)
        if pools:
            logger.info("ghidrecomp_decompilers_disposed pools=%d decompilers=%d", len(pools), disposed)
