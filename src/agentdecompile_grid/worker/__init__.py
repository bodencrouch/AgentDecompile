"""agentdecompile_grid.worker — the node runtime.

``join`` (attach-first), the local agent, capability canaries, the steppable work loop with kill
deadlines, the sandbox, the durable outbox, node identity and invites, and the record bodies the
node writes.

Importing this package registers the canaries in ``core.CANARIES`` and the ``subprocess`` /
``container`` sandboxes in ``sandbox.SANDBOXES`` (both depend on ``core`` only).  Everything
else is resolved lazily (PEP 562) because ``loop``/``outbox``/``agent`` import ``verify.policy``
and ``verify.loop`` imports ``loop`` — eager package-level imports in both directions would be a
cycle whichever package is imported first.
"""
from __future__ import annotations

import importlib
from typing import Any

from . import canaries as canaries  # noqa: F401  (registers CANARIES entries)
from . import sandbox as sandbox  # noqa: F401  (registers SANDBOXES entries)
from .canaries import CanaryReport, PythonCanary, ToolchainCanary, describe_canaries, prove_all, run_canaries
from .identity import Invite, InviteError, Keyring, NodeKey, NodeKeyStore, NodeSigner, assert_two_lineages, bind_identity, independent, make_invite, parse_invite_url
from .records import LogTaskIndex, Proposal, read_results, read_timeouts, read_verdicts
from .sandbox import SANDBOXES, ContainerSandbox, SandboxJob, SubprocessSandbox, deadline_for

_LAZY: dict[str, str] = {
    "AgentClient": "agent", "Endpoint": "agent", "IDLE_POLICIES": "agent", "JoinPlan": "agent", "JoinResult": "agent", "LeaveResult": "agent",
    "LoadAveragePolicy": "agent", "LocalAgent": "agent", "build_loops": "agent", "idle_policy_for": "agent", "join": "agent", "leave": "agent", "open_node_identity": "agent",
    "probe": "agent", "record_writer": "agent", "status": "agent",
    "Candidate": "loop", "PoisonDetector": "loop", "StepEvent": "loop", "StepMachine": "loop", "Upstream": "loop", "WorkLoop": "loop", "WorkerConfig": "loop",
    "FlushReport": "outbox", "Outbox": "outbox", "PendingRecord": "outbox", "RecordWriter": "outbox",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"{__name__}.{module}"), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    "CanaryReport", "ContainerSandbox", "Invite", "InviteError", "Keyring", "LogTaskIndex", "NodeKey", "NodeKeyStore", "NodeSigner", "Proposal", "PythonCanary",
    "SANDBOXES", "SandboxJob", "SubprocessSandbox", "ToolchainCanary", "assert_two_lineages", "bind_identity", "deadline_for", "describe_canaries", "independent",
    "make_invite", "parse_invite_url", "prove_all", "read_results", "read_timeouts", "read_verdicts", "run_canaries", *sorted(_LAZY),
]
