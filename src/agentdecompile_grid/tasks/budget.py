"""agentdecompile_grid.tasks.budget — budget classes to kill deadlines, from configuration.

A task kind declares a ``BudgetClass``; the *worker* owns the deadline (design 2.7).  This module
is the one place that turns a class into seconds:

* ``deadline_for(kind, budget, config)`` — per-kind override (``budgets.per_kind_s``) beats the
  class table (``budgets.micro_s`` ...).  ``UNBOUNDED`` yields 0 and is refused unless
  ``budgets.allow_unbounded``; ``LARGE`` is refused on nodes with ``budgets.allow_large`` off.
* ``timeout_policy(config, kinds)`` — the canonical document a basis includes so a timeout is a
  named, replayable failover: ``{"classes": {...}, "per_kind": {...}, "kill_grace_s": n}``;
  ``timeout_policy_hash`` digests it.
* ``BudgetClock`` — a started deadline: ``remaining()``, ``expired()``, ``check()`` raising
  ``core.Deadline``.  Task kinds that run subprocesses pass ``remaining()`` as the timeout.

Acceptance tests (named here, landed in the verification phase):

* ``test_deadline_per_kind_override_beats_class`` and the override appears in ``timeout_policy``.
* ``test_unbounded_refused_by_name_unless_allowed``.
* ``test_timeout_policy_hash_changes_when_any_deadline_changes``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from ..core import BudgetClass, Deadline as DeadlineError, Refused, TaskSpec, digest_value


@dataclass(frozen=True)
class Deadline:
    """Seconds a task may run and how long the worker waits between SIGTERM and SIGKILL."""

    kind: str
    budget: BudgetClass
    seconds: int
    kill_grace_s: int
    source: str                       # "class" | "per-kind"

    @property
    def hard_kill_s(self) -> int:
        return self.seconds + self.kill_grace_s

    def start(self, now: float | None = None) -> "BudgetClock":
        return BudgetClock(self, started=time.monotonic() if now is None else now)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "budget": self.budget.value, "seconds": self.seconds,
                "kill_grace_s": self.kill_grace_s, "source": self.source}


@dataclass(frozen=True)
class BudgetClock:
    deadline: Deadline
    started: float

    def elapsed(self, now: float | None = None) -> float:
        return (time.monotonic() if now is None else now) - self.started

    def remaining(self, now: float | None = None) -> float:
        if self.deadline.seconds <= 0:
            return float("inf")
        return max(0.0, self.deadline.seconds - self.elapsed(now))

    def expired(self, now: float | None = None) -> bool:
        return self.deadline.seconds > 0 and self.remaining(now) <= 0.0

    def check(self, now: float | None = None) -> None:
        if self.expired(now):
            raise DeadlineError(f"{self.deadline.kind}: budget {self.deadline.budget.value} ({self.deadline.seconds}s) exceeded")


def deadline_for(kind: str, budget: BudgetClass | str, config: Any) -> Deadline:
    budget = BudgetClass(budget)
    if kind in config.budgets.per_kind_s:
        return Deadline(kind=kind, budget=budget, seconds=int(config.budgets.per_kind_s[kind]),
                        kill_grace_s=int(config.budgets.kill_grace_s), source="per-kind")
    return Deadline(kind=kind, budget=budget, seconds=config.deadline_s(budget), kill_grace_s=int(config.budgets.kill_grace_s),
                    source="class")


def deadline_for_spec(spec: TaskSpec, config: Any) -> Deadline:
    return deadline_for(spec.kind, spec.budget, config)


def offerable(budget: BudgetClass | str, config: Any) -> tuple[bool, str]:
    """Whether this node may run tasks of ``budget``; the reason names the config switch when not."""
    budget = BudgetClass(budget)
    if budget is BudgetClass.UNBOUNDED and not config.budgets.allow_unbounded:
        return False, "budget-unbounded-refused"
    if budget is BudgetClass.LARGE and not config.budgets.allow_large:
        return False, "budget-large-not-offered-here"
    return True, ""


def check_offerable(spec: TaskSpec, config: Any) -> None:
    ok, reason = offerable(spec.budget, config)
    if not ok:
        raise Refused(reason)


def budget_table(config: Any) -> dict[str, int]:
    return {b.value: config.deadline_s(b) for b in BudgetClass}


def timeout_policy(config: Any, kinds: Mapping[str, BudgetClass | str] | None = None) -> dict[str, Any]:
    """The canonical timeout policy document (sorted, ints only) a basis may include.

    ``kinds`` (name -> budget class) adds an ``effective`` table with the seconds each named kind
    actually gets on this configuration, so a basis pins what applied, not just the overrides.
    """
    per_kind = {k: int(config.budgets.per_kind_s[k]) for k in sorted(config.budgets.per_kind_s)}
    effective = {name: deadline_for(name, budget, config).seconds for name, budget in sorted((kinds or {}).items())}
    return {"classes": {b.value: int(config.deadline_s(b)) for b in BudgetClass},
            "per_kind": per_kind, "effective": effective, "kill_grace_s": int(config.budgets.kill_grace_s),
            "allow_unbounded": bool(config.budgets.allow_unbounded), "allow_large": bool(config.budgets.allow_large)}


def timeout_policy_hash(config: Any, kinds: Mapping[str, BudgetClass | str] | None = None) -> str:
    return digest_value(timeout_policy(config, kinds))


def describe_budgets(config: Any) -> dict[str, Any]:
    return {"classes": budget_table(config), "per_kind_s": dict(sorted(config.budgets.per_kind_s.items())),
            "kill_grace_s": config.budgets.kill_grace_s, "allow_unbounded": config.budgets.allow_unbounded,
            "allow_large": config.budgets.allow_large, "verify_class": config.budgets.verify_class,
            "timeout_policy_hash": timeout_policy_hash(config)}


__all__ = ["Deadline", "BudgetClock", "deadline_for", "deadline_for_spec", "offerable", "check_offerable",
           "budget_table", "timeout_policy", "timeout_policy_hash", "describe_budgets"]
