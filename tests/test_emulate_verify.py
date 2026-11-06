"""Tests for Unicorn leftover verification (U7)."""

from agentdecompile_recovery.corpus.emulate_verify import verify_leftovers


def test_missing_tool_skipped():
    result = verify_leftovers(
        {"code": b"\x90", "addr": 1},
        [{"code": b"\x90", "addr": 2}],
        static_confidence=90,
    )
    assert result.get("skipped") or result.get("ok") is False


def test_weak_static_refused_even_with_fake_backend():
    def backend(**kwargs):
        return {"ok": True, "ret": 0, "writes": [], "calls": []}

    result = verify_leftovers(
        {"code": b"\x90", "addr": 1},
        [{"code": b"\x90", "addr": 2}],
        static_confidence=40,
        backend=backend,
    )
    assert result["skipped"] is True
    assert result["reason"] == "weak_static"


def test_stub_agreement_marks_verify():
    def backend(**kwargs):
        return {"ok": True, "ret": 7, "writes": [(0, 1)], "calls": ["f"]}

    result = verify_leftovers(
        {"code": b"\x90", "addr": 1},
        [{"code": b"\x90", "addr": 2}],
        static_confidence=90,
        backend=backend,
    )
    assert result["ok"] is True
    assert result["status"] == "verify"
    assert result["identity_only"] is True
