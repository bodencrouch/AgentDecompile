"""Regression tests for review findings on persist / PINNED demotion."""

from agentdecompile_recovery.corpus.propagate import PINNED_KINDS, persist_status


def test_pinned_anchor_demotes_on_canon_key_conflict():
    assert "anchor" in PINNED_KINDS
    result = {"kind": "anchor", "status": "auto", "score": 1.0, "margin": 1.0, "evidence": {}}
    assert persist_status(result, "same_platform", "Foo", "Bar") == "verify"


def test_pinned_anchor_keeps_auto_when_names_agree():
    result = {"kind": "anchor", "status": "auto", "score": 1.0, "margin": 1.0, "evidence": {}}
    assert persist_status(result, "same_platform", "Foo", "Foo") == "auto"
