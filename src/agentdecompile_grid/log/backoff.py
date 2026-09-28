"""Jittered exponential backoff with partition rotation for hot heads.  Pure and seeded.

``full_jitter(policy, seed=...)`` is a generator of ``BackoffStep``; it never sleeps.  The caller
sleeps ``delay_s`` (through an injectable ``sleep``) and, when ``rotate`` is set, moves on to another
partition it holds work for and retries this one later (design §2.2: base 100 ms, cap 5 s, rotate
after 8 consecutive failures).  Jitter strategies are a registry (``full``, ``equal``, ``none``) so a
deployment can pick one as data; the default is full jitter.

``PartitionRotation`` is the deterministic round-robin the outbox uses: start offset from the seed,
``defer`` moves a hot partition to the back, ``order`` returns the current visiting order.

Acceptance tests (named here, written in the verification phase):
  backoff-deterministic: two generators with one seed yield identical delays; the delays never
  exceed ``cap_s``; the ``rotate`` flag fires on every ``rotate_after``-th consecutive failure;
  backoff-rotation: ``PartitionRotation.order`` is a rotation of the sorted input and ``defer`` puts a
  partition last without dropping any.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable, Iterator, Mapping, Sequence

from agentdecompile_grid.core import Registry

JITTERS = Registry("backoff jitter")
"""``name -> Callable[[random.Random, float], float]``: (rng, ceiling) -> delay."""


def _full(rng: random.Random, ceiling: float) -> float:
    return rng.uniform(0.0, ceiling)


def _equal(rng: random.Random, ceiling: float) -> float:
    half = ceiling / 2.0
    return half + rng.uniform(0.0, half)


def _none(rng: random.Random, ceiling: float) -> float:
    return ceiling


JITTERS.register("full", _full)
JITTERS.register("equal", _equal)
JITTERS.register("none", _none)


@dataclass(frozen=True)
class BackoffPolicy:
    """Configuration is data.  Defaults are the design's: 100 ms base, 5 s cap, rotate after 8; plus a
    bound of 128 attempts so a wedged head becomes a named ``AppendGaveUp``, never a silent hang."""

    base_s: float = 0.1
    cap_s: float = 5.0
    multiplier: float = 2.0
    rotate_after: int = 8
    max_attempts: int | None = 128     # ~10 min of capped sleeps; None = retry forever (explicit opt-in)
    jitter: str = "full"

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> BackoffPolicy:
        return cls(
            base_s=float(config.get("base_s", 0.1)), cap_s=float(config.get("cap_s", 5.0)),
            multiplier=float(config.get("multiplier", 2.0)), rotate_after=int(config.get("rotate_after", 8)),
            max_attempts=(int(config["max_attempts"]) if config.get("max_attempts", 128) is not None else None),
            jitter=str(config.get("jitter", "full")),
        )

    @classmethod
    def config_schema(cls) -> dict[str, Any]:
        return {"type": "object", "properties": {
            "base_s": {"type": "number", "default": 0.1}, "cap_s": {"type": "number", "default": 5.0},
            "multiplier": {"type": "number", "default": 2.0}, "rotate_after": {"type": "integer", "default": 8},
            "max_attempts": {"type": ["integer", "null"], "default": 128, "description": "null = retry forever"},
            "jitter": {"enum": JITTERS.names(), "default": "full"}}}


DEFAULT_BACKOFF = BackoffPolicy()


@dataclass(frozen=True)
class BackoffStep:
    attempt: int      # 1-based count of consecutive failures on the current key
    delay_s: float    # what to sleep before the next try
    rotate: bool      # True on every ``rotate_after``-th failure: move to another partition first


def full_jitter(policy: BackoffPolicy = DEFAULT_BACKOFF, *, seed: int = 0) -> Iterator[BackoffStep]:
    """Yield one step per failure; stops after ``max_attempts`` when set.  Never sleeps itself."""
    rng = random.Random(seed)
    jitter = JITTERS.get(policy.jitter)
    attempt = 0
    while policy.max_attempts is None or attempt < policy.max_attempts:
        attempt += 1
        ceiling = min(policy.cap_s, policy.base_s * (policy.multiplier ** (attempt - 1)))
        delay = jitter(rng, ceiling)
        yield BackoffStep(attempt=attempt, delay_s=delay, rotate=policy.rotate_after > 0 and attempt % policy.rotate_after == 0)


def delays(policy: BackoffPolicy, *, seed: int, count: int) -> list[float]:
    """The first ``count`` delays for a seed; handy for the harness and for reporting."""
    out: list[float] = []
    for step in full_jitter(policy, seed=seed):
        out.append(step.delay_s)
        if len(out) >= count:
            break
    return out


class PartitionRotation:
    """Deterministic round-robin over the partitions a writer holds work for."""

    def __init__(self, partitions: Sequence[str] = (), *, seed: int = 0) -> None:
        self._order: list[str] = sorted(set(partitions))
        self._seed = seed
        if self._order:
            offset = random.Random(seed).randrange(len(self._order))
            self._order = self._order[offset:] + self._order[:offset]

    def order(self) -> list[str]:
        return list(self._order)

    def add(self, partition: str) -> None:
        if partition not in self._order:
            self._order.append(partition)

    def remove(self, partition: str) -> None:
        if partition in self._order:
            self._order.remove(partition)

    def defer(self, partition: str) -> None:
        """Move a hot partition to the back; the others get their turn first."""
        if partition in self._order:
            self._order.remove(partition)
            self._order.append(partition)

    def advance(self) -> None:
        if self._order:
            self._order = self._order[1:] + self._order[:1]

    def __len__(self) -> int:
        return len(self._order)

    def __iter__(self) -> Iterator[str]:
        return iter(self.order())


Sleeper = Callable[[float], None]

__all__ = ["BackoffPolicy", "BackoffStep", "DEFAULT_BACKOFF", "JITTERS", "PartitionRotation", "Sleeper", "delays", "full_jitter"]
