"""Tests for the anonymization gate (``scripts/check-anonymization.sh``).

The gate is exercised against a synthetic tree with a synthetic denylist of
made-up tokens. The real denylist is only ever read to count matches; its
contents are never printed and never appear in an assertion message.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("rg") is None or shutil.which("git") is None, reason="needs rg and git"),
]

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-anonymization.sh"
BASELINE_FILE = REPO_ROOT / "scripts" / "anonymization-baseline.json"
SYNTHETIC_TOKENS = ("zqproductzq", "two word phrase")
FILENAME_HIT = "docs/zqproductzq-guide.md"
NOTE_FILE = "docs/note.md"
IDENT_FILE = "tests/ident.py"
UNDERSCORE_FILE = "src/under.py"


def digest(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def leak_count(text: str) -> int:
    lowered = text.lower()
    return sum(lowered.count(token) for token in SYNTHETIC_TOKENS)


class Gate:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "tree"
        self.outside = tmp_path / "outside"
        self.outside.mkdir()
        self.denylist = self.outside / "denylist.txt"
        self.baseline = self.outside / "baseline.json"
        self.denylist.write_text("# synthetic denylist\n\nzqproductzq\nTwo Word Phrase\nzqproductzq\n")
        self.env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "AGENT_DECOMPILE_NAME_DENYLIST": str(self.denylist),
            "AGENT_DECOMPILE_NAME_BASELINE": str(self.baseline),
        }
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.root / "scripts" / SCRIPT.name)
        self.write("src/clean.py", "nothing to see\nzqproductzqfoo is glued\n")
        self.write(NOTE_FILE, "line one zqproductzq\nZQPRODUCTZQ again\nsee the two word phrase here\nclean line\n")
        self.write(FILENAME_HIT, "clean body\n")
        self.write(IDENT_FILE, "name = 'zqproductzqfoo'\nother = fooZqproductzq\nphrase = twowordphrase\n")
        self.write(UNDERSCORE_FILE, "zqproductzq_bar = 1\nx = two_word_phrase\ny = TWO-WORD-PHRASE\nz = 'two  word   phrase'\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")

    def write(self, rel: str, text: str) -> None:
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, env=self.env, check=True, capture_output=True)

    def run(self, *flags: str, **env_overrides: str | None) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = subprocess.run(["bash", str(self.root / "scripts" / SCRIPT.name), *flags], cwd=self.root, env=env, capture_output=True, text=True)
        assert leak_count(result.stdout + result.stderr) == 0, "gate output leaked a denylist token"
        return result

    def baseline_paths(self) -> dict[str, int]:
        return json.loads(self.baseline.read_text())["paths"]


@pytest.fixture
def gate(tmp_path: Path) -> Gate:
    return Gate(tmp_path)


def test_missing_denylist_exits_2(gate: Gate) -> None:
    result = gate.run(AGENT_DECOMPILE_NAME_DENYLIST=str(gate.outside / "absent.txt"))
    assert result.returncode == 2
    assert "AGENT_DECOMPILE_NAME_DENYLIST" in result.stdout
    assert "one token or phrase per line" in result.stdout


def test_empty_denylist_exits_2(gate: Gate) -> None:
    gate.denylist.write_text("# only a comment\n\n")
    result = gate.run()
    assert result.returncode == 2


def test_absent_baseline_fails_on_any_hit(gate: Gate) -> None:
    result = gate.run()
    assert result.returncode == 1
    assert "baseline absent" in result.stdout
    assert "3 new path(s)" in result.stdout


def test_write_baseline_records_hashed_counts(gate: Gate) -> None:
    result = gate.run("--write-baseline")
    assert result.returncode == 0
    assert "3 entries, 8 hits (added 3, removed 0, shrank 0, grew 0)" in result.stdout
    paths = gate.baseline_paths()
    assert paths == {digest(NOTE_FILE): 3, digest(FILENAME_HIT): 1, digest(UNDERSCORE_FILE): 4}
    assert list(paths) == sorted(paths)
    assert all(re.fullmatch(r"[0-9a-f]{16}", key) for key in paths)


def test_filename_hit_counts_and_identifier_substring_does_not(gate: Gate) -> None:
    gate.run("--write-baseline")
    paths = gate.baseline_paths()
    assert paths[digest(FILENAME_HIT)] == 1
    assert digest(IDENT_FILE) not in paths
    assert digest("src/clean.py") not in paths
    assert paths[digest(UNDERSCORE_FILE)] == 4


def test_hits_equal_to_baseline_pass(gate: Gate) -> None:
    gate.run("--write-baseline")
    result = gate.run()
    assert result.returncode == 0
    assert result.stdout.rstrip().endswith("Anonymization gate OK (baseline: 3 paths, 8 hits)")


def test_new_path_with_hit_fails_ratchet(gate: Gate) -> None:
    gate.run("--write-baseline")
    gate.write("src/fresh.py", "zqproductzq crept in\n")
    gate.git("add", "-A")
    result = gate.run()
    assert result.returncode == 1
    assert "1 new path(s), 0 grown path(s)" in result.stdout
    assert f"{digest('src/fresh.py')}     1  NEW" in result.stdout


def test_count_growth_on_known_path_fails_ratchet(gate: Gate) -> None:
    gate.run("--write-baseline")
    gate.write(NOTE_FILE, (gate.root / NOTE_FILE).read_text() + "one more zqproductzq\n")
    result = gate.run()
    assert result.returncode == 1
    assert "0 new path(s), 1 grown path(s)" in result.stdout
    assert f"{digest(NOTE_FILE)}     4  GREW (baseline 3)" in result.stdout


def test_count_decrease_passes_without_touching_baseline(gate: Gate) -> None:
    gate.run("--write-baseline")
    before = gate.baseline.read_text()
    gate.write(NOTE_FILE, "clean now\n")
    result = gate.run()
    assert result.returncode == 0
    assert gate.baseline.read_text() == before


def test_write_baseline_after_growth_then_pass(gate: Gate) -> None:
    gate.run("--write-baseline")
    gate.write(NOTE_FILE, (gate.root / NOTE_FILE).read_text() + "one more zqproductzq\n")
    gate.write(FILENAME_HIT, "")
    (gate.root / IDENT_FILE).unlink()
    gate.git("add", "-A")
    result = gate.run("--write-baseline")
    assert result.returncode == 0
    assert "(added 0, removed 0, shrank 0, grew 1)" in result.stdout
    assert gate.run().returncode == 0
    (gate.root / FILENAME_HIT).unlink()
    gate.git("add", "-A")
    result = gate.run("--write-baseline")
    assert "2 entries, 8 hits (added 0, removed 1, shrank 0, grew 0)" in result.stdout


def test_strict_ignores_baseline(gate: Gate) -> None:
    gate.run("--write-baseline")
    result = gate.run("--strict")
    assert result.returncode == 1
    assert "Anonymization gate FAILED (strict): 8 hits over 3 paths" in result.stdout
    for rel in (NOTE_FILE, FILENAME_HIT, UNDERSCORE_FILE):
        (gate.root / rel).unlink()
    gate.git("add", "-A")
    result = gate.run("--strict")
    assert result.returncode == 0
    assert result.stdout.rstrip().endswith("Anonymization gate OK (strict: 0 hits)")


def test_strict_and_write_baseline_conflict(gate: Gate) -> None:
    assert gate.run("--strict", "--write-baseline").returncode == 2
    assert gate.run("--bogus").returncode == 2


def test_corrupt_baseline_exits_2(gate: Gate) -> None:
    gate.baseline.write_text('{"version": 7}\n')
    assert gate.run().returncode == 2


def test_output_never_contains_a_token(gate: Gate) -> None:
    outputs = [gate.run(), gate.run("--strict"), gate.run("--write-baseline"), gate.run()]
    combined = "".join(r.stdout + r.stderr for r in outputs)
    assert leak_count(combined) == 0
    assert leak_count(gate.baseline.read_text()) == 0


def _real_denylist_regex() -> re.Pattern[str] | None:
    path = Path(os.environ.get("AGENT_DECOMPILE_NAME_DENYLIST") or Path.home() / ".config" / "agentdecompile" / "name-denylist.txt")
    if not path.is_file():
        return None
    tokens = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
    if not tokens:
        return None
    alternatives = "|".join(r"[\s_-]+".join(re.escape(piece) for piece in token.split()) for token in tokens)
    return re.compile(rf"(^|[^A-Za-z0-9])({alternatives})([^A-Za-z0-9]|$)", re.IGNORECASE)


def test_gate_files_contain_no_real_denylist_token() -> None:
    pattern = _real_denylist_regex()
    if pattern is None:
        pytest.skip("real denylist not present on this machine")
    checked = [SCRIPT, Path(__file__)]
    if BASELINE_FILE.is_file():
        checked.append(BASELINE_FILE)
    leaks = sum(len(pattern.findall(path.read_text(encoding="utf-8"))) for path in checked)
    assert leaks == 0, f"{leaks} denylist match(es) across {len(checked)} gate file(s)"
