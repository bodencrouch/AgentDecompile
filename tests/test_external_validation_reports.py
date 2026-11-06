"""External report semantics through the public reader; no provider execution."""
import json
import pytest
from agentdecompile_recovery.corpus.external_validation import InvalidReport, normalize_report


def benchmark(matched=True, expected=True, cases=2):
    return {"schema_version": 1, "total": 1, "expectations_met": int(matched == expected),
            "results": [{"name": "owned-fixture", "matched": matched, "expected_match": expected,
                         "cases_run": cases, "findings": [], "duration_s": 0.1}]}


def normalize(data, provider="reagent-benchmark"):
    return normalize_report(json.dumps(data).encode(), provider)


def test_expected_negative_is_not_candidate_success():
    result = normalize(benchmark(False, False))
    check = result["checks"][0]
    assert check["expectation_met"] is True
    assert check["outcome"] == "mismatched"
    assert result["recovery_accepted"] is False
    assert result["provenance_verified"] is False
    assert result["execution_state"] == "unknown"


def test_zero_test_cases_do_not_establish_a_match():
    assert normalize(benchmark(cases=0))["checks"][0]["outcome"] == "unknown"


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]", b'{"schema_version":1,"schema_version":1}',
                                  b'{"schema_version":NaN}', b'not json'])
def test_empty_malformed_and_ambiguous_reports_refused(raw):
    with pytest.raises(InvalidReport):
        normalize_report(raw, "reagent-benchmark")


@pytest.mark.parametrize("change", [{"schema_version": 2}, {"schema_version": True},
                                     {"total": 2}, {"results": []}, {"expectations_met": 0}])
def test_unrecognized_or_inconsistent_benchmark_refused(change):
    with pytest.raises(InvalidReport):
        normalize({**benchmark(), **change})


def test_boolean_is_not_accepted_as_case_count():
    with pytest.raises(InvalidReport):
        normalize(benchmark(cases=True))


def test_reccmp_exact_score_is_only_scoped_diagnostic():
    result = normalize({"file": "original.exe", "format": 1, "timestamp": 1,
                        "data": [{"address": "0x401000", "name": "f", "matching": 1.0,
                                  "recomp": "various", "stub": True}]}, "reccmp-compare")
    assert result["checks"][0]["outcome"] == "observed"
    assert result["checks"][0]["provider_details"]["stub"] is True
    assert result["coverage"]["eligible_denominator"] == "unknown"
    assert result["recovery_accepted"] is False


def test_empty_reccmp_report_not_zero_mismatches():
    with pytest.raises(InvalidReport):
        normalize({"file": "original.exe", "format": 1, "timestamp": 1, "data": []}, "reccmp-compare")


def test_cli_and_catalog_read_report_without_provider_execution(tmp_path, capsys):
    from agentdecompile_recovery.corpus.cli import main
    from agentdecompile_recovery.corpus.dashboard.actions.introspect import corpus_specs
    path = tmp_path / "report.json"
    path.write_text(json.dumps(benchmark(False, False)))
    assert main(["normalize-validation-report", "--provider", "reagent-benchmark", "--report", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["checks"][0]["outcome"] == "mismatched"
    action = {a.id: a for a in corpus_specs()}["corpus.normalize-validation-report"]
    assert not action.mutating and not action.ghidra_exclusive
    path.write_text('{}')
    assert main(["normalize-validation-report", "--provider", "reagent-benchmark", "--report", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["report_state"] == "invalid_output"


def test_deep_json_and_overflow_are_invalid_reports_not_cli_crashes():
    with pytest.raises(InvalidReport):
        normalize_report(b"[" * 2000 + b"0" + b"]" * 2000, "reagent-benchmark")
    data = benchmark()
    data["results"][0]["duration_s"] = 10 ** 400
    with pytest.raises(InvalidReport):
        normalize(data)


def test_nonfinite_nested_provider_details_refused_before_projection():
    raw = b'{"file":"a.exe","format":1,"timestamp":1,"data":[{"address":"0x1","name":"f","matching":1,"diff":{"value":1e999}}]}'
    with pytest.raises(InvalidReport):
        normalize_report(raw, "reccmp-compare")
