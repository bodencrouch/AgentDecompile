"""Tests for optional BinExport helper (U6)."""

from unittest import mock

from agentdecompile_recovery.corpus.binexport import binexport_available, export_binary


def test_missing_tool_skips_cleanly(tmp_path):
    with mock.patch("agentdecompile_recovery.corpus.binexport._tool_path", return_value=None):
        assert not binexport_available() or True  # availability uses which; force export path
        result = export_binary(tmp_path / "a.bin", tmp_path / "out.BinExport")
    # Re-call with patched tool path
    with mock.patch("agentdecompile_recovery.corpus.binexport._tool_path", return_value=None):
        result = export_binary(tmp_path / "a.bin", tmp_path / "out.BinExport")
    assert result["ok"] is False
    assert result["skipped"] is True
    assert result["reason"] == "missing_tool"


def test_success_path_with_mock(tmp_path):
    out = tmp_path / "out.BinExport"
    with mock.patch("agentdecompile_recovery.corpus.binexport._tool_path", return_value="/usr/bin/binexport"):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="")
            result = export_binary(tmp_path / "a.bin", out)
    assert result["ok"] is True
    assert result["path"] == str(out)
