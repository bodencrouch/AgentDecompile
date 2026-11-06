"""Optional Unicorn/QEMU leftover verification.

Runs only after strong static evidence and ≤3 candidates. Dynamic agreement
cannot rescue weak static alone. Identity evidence only — not objdiff-0.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


def unicorn_available() -> bool:
    try:
        import unicorn  # noqa: F401

        return True
    except Exception:
        return False


def emulate_side_effects(
    *,
    code: bytes,
    entry: int = 0,
    arch: str = "x86",
    bits: int = 32,
    backend: Callable[..., dict] | None = None,
) -> dict[str, Any]:
    """Return normalized side effects {ret, writes, calls} or skipped."""
    if backend is not None:
        return backend(code=code, entry=entry, arch=arch, bits=bits)
    if not unicorn_available():
        return {"ok": False, "skipped": True, "reason": "missing_unicorn"}
    # Full Unicorn harness is environment-specific; default is skip-safe stub.
    return {"ok": False, "skipped": True, "reason": "harness_not_configured"}


def compare_effects(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if not a.get("ok") or not b.get("ok"):
        return False
    return (
        a.get("ret") == b.get("ret")
        and list(a.get("calls") or []) == list(b.get("calls") or [])
        and set(map(tuple, a.get("writes") or [])) == set(map(tuple, b.get("writes") or []))
    )


def verify_leftovers(
    reference: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    static_confidence: int,
    high_band: int = 80,
    max_candidates: int = 3,
    backend: Callable[..., dict] | None = None,
) -> dict[str, Any]:
    """Emulate reference + ≤3 candidates when static band is high enough."""
    if static_confidence < high_band:
        return {"ok": False, "skipped": True, "reason": "weak_static"}
    if len(candidates) > max_candidates:
        candidates = list(candidates)[:max_candidates]
    if not candidates:
        return {"ok": False, "skipped": True, "reason": "no_candidates"}
    ref_fx = emulate_side_effects(
        code=bytes(reference.get("code") or b""),
        entry=int(reference.get("entry") or 0),
        arch=str(reference.get("arch") or "x86"),
        bits=int(reference.get("bits") or 32),
        backend=backend,
    )
    if ref_fx.get("skipped"):
        return {"ok": False, **ref_fx}
    agreements = []
    for cand in candidates:
        fx = emulate_side_effects(
            code=bytes(cand.get("code") or b""),
            entry=int(cand.get("entry") or 0),
            arch=str(cand.get("arch") or reference.get("arch") or "x86"),
            bits=int(cand.get("bits") or reference.get("bits") or 32),
            backend=backend,
        )
        if compare_effects(ref_fx, fx):
            agreements.append(cand.get("addr") or cand.get("id"))
    return {
        "ok": bool(agreements),
        "agreements": agreements,
        "status": "verify" if len(agreements) == 1 else "ambiguous",
        "identity_only": True,
    }


__all__ = [
    "compare_effects",
    "emulate_side_effects",
    "unicorn_available",
    "verify_leftovers",
]
