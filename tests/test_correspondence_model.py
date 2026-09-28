"""Tests for Correspondence evidence model (U9)."""

from agentdecompile_recovery.corpus.correspondence import ambiguity_group, enrich_evidence


def test_duplicate_fingerprint_becomes_ambiguity_group():
    ev = ambiguity_group([{"dst": 1, "score": 0.9}, {"dst": 2, "score": 0.9}])
    assert ev["status_band"] == "ambiguous"
    assert ev["identity_claim"] is False
    assert len(ev["alternatives"]) == 2


def test_inline_relation_persists():
    ev = enrich_evidence({}, kind="inline", status="review", relation="inline")
    assert ev["relation"] == "inline"
    assert ev["status_band"] == "tentative"
    assert ev["identity_claim"] is False


def test_quarantine_flag():
    ev = enrich_evidence({}, quarantine=True)
    assert ev["status_band"] == "quarantined"
    assert ev["quarantine"] is True
