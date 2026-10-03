from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import unittest
from unittest.mock import patch

from agentdecompile_recovery.corpus.dashboard.panels import crossmatch, stabs


class DashboardQueryShapeTests(unittest.TestCase):
    def test_stabs_provenance_reads_binary_facts_not_func_rows(self):
        queries = []

        def query(sql, params=(), **_kwargs):
            queries.append(sql)
            if "FROM binary" in sql:
                return [(1, "/GameA/example.exe", "example", "win", "game-a", "x86",
                         100, 75)], None
            self.fail(f"unexpected query: {sql}")

        with patch.object(stabs, "query_db", side_effect=query), \
             patch.object(stabs, "load_json", return_value=(None, "missing")):
            sec = stabs._collect_provenance()
            html = stabs._render_provenance(sec)

        self.assertTrue(queries)
        self.assertFalse(any("FROM func" in sql for sql in queries))
        self.assertEqual(sec["binaries"][0]["placeholders"], 25)
        self.assertIn("25", html)
        self.assertIn("offline summary", html)

    def test_crossmatch_matrix_uses_offline_report_not_match_group_by(self):
        report = (
            "| source | target | status | count | mean score |\n"
            "|---|---|---|---:|---:|\n"
            "| `source.exe` | `target.exe` | review | 1,200 | 0.8 |\n"
            "| `source.exe` | `target.exe` | auto | 34 | 0.9 |\n"
        )
        queries = []

        def query(sql, params=(), **_kwargs):
            queries.append(sql)
            return [
                (1, "GameA__source.exe", "/game/source.exe", "", "", 10),
                (2, "GameA__target.exe", "/game/target.exe", "", "", 10),
            ], None

        with patch("pathlib.Path.read_text", return_value=report), \
             patch.object(crossmatch, "query_db", side_effect=query):
            binaries, err = crossmatch._binaries()
            facts = crossmatch._matrix_facts(binaries, err)
            html = crossmatch._matrix_section({"matrix": facts})

        self.assertTrue(queries)
        self.assertTrue(all("FROM binary" in sql for sql in queries))
        self.assertFalse(any("FROM match" in sql for sql in queries))
        self.assertEqual(facts["rows"], ["GameA__source.exe"])
        self.assertEqual(facts["cols"], ["GameA__target.exe"])
        self.assertEqual(facts["total"], 1234)
        self.assertIn("1,234", html)
        self.assertIn("GameA__source.exe", html)
        self.assertIn("GameA__target.exe", html)

    def test_crossmatch_missing_summary_does_not_fall_back_to_scan(self):
        with patch("pathlib.Path.read_text", side_effect=OSError("gone")), \
             patch.object(crossmatch, "query_db") as query:
            facts = crossmatch._matrix_facts([], None)
            html = crossmatch._matrix_section({"matrix": facts})
        query.assert_not_called()
        self.assertEqual(facts["state"], "missing")
        self.assertIn("summary unavailable", html)
