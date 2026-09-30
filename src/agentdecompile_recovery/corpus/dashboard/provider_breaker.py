"""One shared recovery probe per provider after a crash (U9 FP-10).

When a provider crashes, every waiting task used to make its own failing call. That
spent each task's attempts and kept knocking on a provider that was restarting. A
breaker per provider opens on a crash-signature failure. While it is open, callers get
an immediate "recovering" answer instead of a call. After a cooldown exactly one caller
is let through as the probe; its success closes the breaker, its failure reopens it.
Healing is bounded: after ``max_probes`` failed probes the provider is reported
unavailable until an operator resets it. Other providers are unaffected.
"""
from __future__ import annotations

import threading
import time

CRASH_SIGNATURES = ("connection refused", "connection reset", "broken pipe", "remote end closed",
                    "server disconnected", "eof occurred", "connection aborted")


def is_crash(text: str) -> bool:
    lowered = (text or "").lower()
    return any(sig in lowered for sig in CRASH_SIGNATURES)


class ProviderBreaker:
    def __init__(self, *, cooldown_s: float = 5.0, max_probes: int = 6, clock=time.monotonic) -> None:
        self.cooldown_s, self.max_probes, self._clock = cooldown_s, max_probes, clock
        self._lock = threading.Lock()
        self.state = "closed"          # closed | open | probing | unavailable
        self.opened_at = 0.0
        self.failed_probes = 0
        self.probe_owner: str | None = None
        self.refused = 0

    def admit(self, caller: str) -> tuple[bool, str]:
        """``(True, "")`` to call the provider, else ``(False, reason)`` to wait."""
        with self._lock:
            if self.state == "closed":
                return True, ""
            if self.state == "unavailable":
                self.refused += 1
                return False, (f"provider unavailable after {self.failed_probes} failed recovery probes; "
                               "an operator reset is required")
            if self.state == "open" and self._clock() - self.opened_at >= self.cooldown_s:
                self.state, self.probe_owner = "probing", caller
                return True, ""
            self.refused += 1
            return False, "provider temporarily unavailable: recovering; one shared probe is in progress"

    def record(self, caller: str, *, crashed: bool) -> None:
        with self._lock:
            probing = self.state == "probing" and self.probe_owner == caller
            if not crashed:
                if self.state == "closed" or probing:
                    self.state, self.failed_probes, self.probe_owner = "closed", 0, None
                return
            if probing:
                self.failed_probes += 1
                self.probe_owner = None
                if self.failed_probes >= self.max_probes:
                    self.state = "unavailable"
                    return
            if self.state in ("closed", "probing"):
                self.state, self.opened_at = "open", self._clock()

    def release(self, caller: str) -> None:
        """A probe that ended without observing the provider (refused, raised) frees the slot."""
        with self._lock:
            if self.state == "probing" and self.probe_owner == caller:
                self.state, self.probe_owner, self.opened_at = "open", None, self._clock() - self.cooldown_s

    def reset(self) -> None:
        with self._lock:
            self.state, self.failed_probes, self.probe_owner = "closed", 0, None

    def status(self) -> dict:
        with self._lock:
            return {"state": self.state, "failedProbes": self.failed_probes, "maxProbes": self.max_probes,
                    "refusedWhileRecovering": self.refused}


_BREAKERS: dict[str, ProviderBreaker] = {}
_BREAKERS_LOCK = threading.Lock()


def breaker_for(provider: str) -> ProviderBreaker:
    with _BREAKERS_LOCK:
        return _BREAKERS.setdefault(provider, ProviderBreaker())
