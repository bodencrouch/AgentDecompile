from __future__ import annotations

import pytest

from agentdecompile_recovery.corpus.export_run_report import match_source

pytestmark = pytest.mark.unit


def test_match_source_keeps_identity_and_seed_evidence_separate() -> None:
    assert match_source(7, "seed-validation-byte-exact:results.jsonl") == "recorded-seed-evidence"
    assert match_source(7, "original-ledger.json") == "recorded-source-with-logical-identity"
    assert match_source(None, "original-ledger.json") == "recorded-source"
