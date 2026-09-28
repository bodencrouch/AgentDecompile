import json
from pathlib import Path


def test_shipped_sleigh_expected_agreement_is_pinned() -> None:
    path = Path("native/bench/expected_agreement/shipped-sleigh-12.1.3.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "agentdecompile.native-expected-agreement/v0"
    assert payload["binary"]["sha256"] == "593d75ff9eebbf7a972a6a06307c860b2335e128bdf09b6e5fe1e628b6087863"
    assert payload["snapshot"]["producer_ghidra_version"] == "12.1.3"
    assert payload["snapshot"]["engine_sig_major"] == 6
    assert payload["snapshot"]["engine_sig_minor"] == 1
    agreement = payload["differential"]["expected_agreement"]
    classified = (
        agreement["match"]
        + agreement["mismatch_layout_only"]
        + agreement["mismatch_content"]
        + agreement["native_error"]
        + agreement["native_timeout"]
        + agreement["native_crash"]
        + agreement["oracle_absent"]
        + agreement["native_missing_dependency"]
    )
    assert payload["differential"]["parity_ok"] is False
    assert payload["differential"]["parity_errors"] == [
        "native SLEIGH hash drift coincides with mismatch-content results"
    ]
    assert payload["differential"]["parity_warnings"]
    assert agreement["total_results"] == payload["snapshot"]["ok"]
    assert classified == agreement["total_results"]
    assert agreement["native_crash"] == 0
