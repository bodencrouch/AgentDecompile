"""agentdecompile_grid — reusable, content-addressed, log-structured distributed compute.

The grid never imports the recovery pipeline.  See ``core`` for the contract every layer
implements; adapters register themselves on import of their package.
"""
from __future__ import annotations

from .core import GRID_SCHEMA_VERSION  # noqa: F401

__version__ = "0.1.0"
