"""U30 tests for U4's multi-project session merge/dedupe (R-session support).

Converted from the U4 inline verification sequence: two distinct projects
both stay visible after a merge, the same project opened twice collapses to
one record, a locator that only differs by a trailing slash aliases to the
same project, and a stale-revision write merges in (keeps) the other
project that write did not mention. The last test documents -- as a
characterization test, not an endorsement -- that a *current*-revision
write omitting a project currently drops it.
"""

from __future__ import annotations

import pytest

from agentdecompile_recovery.corpus.ghidra_project import (
    load_sessions,
    save_sessions_merged,
)

pytestmark = pytest.mark.unit


def _session(sid, locator, title="Untitled"):
    return {"id": sid, "title": title, "locator": locator, "imports": []}


def test_two_distinct_projects_both_visible(tmp_path) -> None:
    save_sessions_merged(
        tmp_path,
        {"revision": 0, "active": "s1", "sessions": [_session("s1", "/repo/a.gpr")]},
    )
    stored = load_sessions(tmp_path)
    result = save_sessions_merged(
        tmp_path,
        {
            "revision": stored["revision"],
            "active": "s2",
            "sessions": [*stored["sessions"], _session("s2", "/repo/b.gpr")],
        },
    )

    locators = {s["locator"] for s in result["sessions"]}
    assert "/repo/a.gpr" in locators
    assert "/repo/b.gpr" in locators
    assert len(result["sessions"]) == 2


def test_same_project_opened_twice_dedupes(tmp_path) -> None:
    save_sessions_merged(
        tmp_path,
        {"revision": 0, "active": "s1", "sessions": [_session("s1", "/repo/a.gpr")]},
    )
    stored = load_sessions(tmp_path)
    # A second client-local session id pointing at the same locator.
    result = save_sessions_merged(
        tmp_path,
        {
            "revision": stored["revision"],
            "active": "s2",
            "sessions": [*stored["sessions"], _session("s2", "/repo/a.gpr")],
        },
    )

    matching = [s for s in result["sessions"] if s["locator"] == "/repo/a.gpr"]
    assert len(matching) == 1


def test_trailing_slash_alias_collapses_to_same_project(tmp_path) -> None:
    save_sessions_merged(
        tmp_path,
        {"revision": 0, "active": "s1", "sessions": [_session("s1", "/repo/a.gpr")]},
    )
    stored = load_sessions(tmp_path)
    result = save_sessions_merged(
        tmp_path,
        {
            "revision": stored["revision"],
            "active": "s2",
            "sessions": [*stored["sessions"], _session("s2", "/repo/a.gpr/")],
        },
    )

    matching = [s for s in result["sessions"] if s["locator"].rstrip("/") == "/repo/a.gpr"]
    assert len(matching) == 1


def test_stale_revision_write_keeps_the_other_project(tmp_path) -> None:
    save_sessions_merged(
        tmp_path,
        {
            "revision": 0,
            "active": "s1",
            "sessions": [_session("s1", "/repo/a.gpr"), _session("s2", "/repo/b.gpr")],
        },
    )
    stored = load_sessions(tmp_path)
    stale_revision = stored["revision"] - 1  # intentionally behind current

    result = save_sessions_merged(
        tmp_path,
        {
            "revision": stale_revision,
            "active": "s1",
            # This stale write only knows about project a; project b is
            # absent from its payload, but must still survive the merge.
            "sessions": [_session("s1", "/repo/a.gpr", title="Renamed")],
        },
    )

    assert result.get("merged") is True
    locators = {s["locator"] for s in result["sessions"]}
    assert "/repo/a.gpr" in locators
    assert "/repo/b.gpr" in locators


def test_current_revision_write_omitting_a_project_drops_it_characterization(tmp_path) -> None:
    """Characterization test: documents current behavior, not a requirement.

    Unlike a stale-revision write (which merges and therefore preserves
    projects the payload didn't mention), a write at the *current* stored
    revision is taken as authoritative and simply replaces the session list.
    If a caller computes its payload from a view that omitted project b,
    project b is silently dropped. This is today's actual behavior in
    `save_sessions_merged`, captured here so a future change to it is a
    deliberate decision, not an accident.
    """
    save_sessions_merged(
        tmp_path,
        {
            "revision": 0,
            "active": "s1",
            "sessions": [_session("s1", "/repo/a.gpr"), _session("s2", "/repo/b.gpr")],
        },
    )
    stored = load_sessions(tmp_path)
    current_revision = stored["revision"]

    result = save_sessions_merged(
        tmp_path,
        {
            "revision": current_revision,
            "active": "s1",
            "sessions": [_session("s1", "/repo/a.gpr")],  # omits project b
        },
    )

    locators = {s["locator"] for s in result["sessions"]}
    assert locators == {"/repo/a.gpr"}
    assert "/repo/b.gpr" not in locators
