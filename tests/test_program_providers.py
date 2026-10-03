"""U30 tests for U6's CodeBrowser provider read endpoints (R11).

Converted from the U6 inline verification sequence. The "unknown kind"
rejection happens before any Ghidra store is touched, so it is covered here
with a synthetic locator/program and no real Ghidra project. The four
readers themselves (equates, relocations, bookmarks, defined_strings) only
produce meaningful rows against a real Ghidra DB, which this repo's test
fixtures do not provide -- per the tests-last constraint to avoid depending
on the external corpus/Ghidra project paths, those reader bodies are skipped
here with an explicit reason rather than faked against a mocked program
object that would not exercise the real DB-reading code.
"""

from __future__ import annotations

import pytest

from agentdecompile_recovery.corpus.dashboard.workbench import (
    _PROVIDER_KINDS,
    program_providers,
)

pytestmark = pytest.mark.unit


def test_unknown_provider_kind_returns_ok_false_with_expected_error() -> None:
    result = program_providers("some-locator", "some-program", "bogus-kind")

    assert result["ok"] is False
    assert "unknown provider kind" in result["error"]
    assert "bogus-kind" in result["error"]
    assert result["kind"] == "bogus-kind"
    assert result["results"] == []
    assert result["hasMore"] is False


def test_missing_locator_or_program_is_required_error() -> None:
    result = program_providers("", "", "equates")

    assert result["ok"] is False
    assert result["error"] == "locator and program are required"


@pytest.mark.parametrize("kind", _PROVIDER_KINDS)
def test_known_kind_accepted_by_validation_before_store_lookup(kind) -> None:
    # A known kind passes the validation gate and proceeds to look the
    # program up in the on-disk store, which does not exist here.
    result = program_providers("/nonexistent/locator", "no-such-program", kind)

    assert result["ok"] is False
    assert "error" in result
    # It must not be the "unknown provider kind" branch: the kind was valid.
    assert "unknown provider kind" not in result["error"]


@pytest.mark.skip(
    reason=(
        "equates/relocations/bookmarks/defined_strings readers only produce "
        "real rows against a live Ghidra DB (prog.equates()/relocations()/"
        "bookmarks()/defined_strings()); no synthetic Ghidra project fixture "
        "is available in this repo's test assets, and the tests-last rule "
        "forbids depending on the external corpus DB or real Ghidra project "
        "paths. Exercise these four readers manually against a real Ghidra "
        "DB per the U6 verification log instead."
    )
)
def test_four_readers_against_real_ghidra_db() -> None:
    raise AssertionError("unreachable: skipped")
