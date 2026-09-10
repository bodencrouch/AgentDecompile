from pathlib import Path

import pytest

from agentdecompile_recovery.native_snapshot.bench import CompletionMismatch, CorpusMismatch, Lane, report, verify_corpus, write_report


def lane(name: str, wall: float, addresses: tuple[str, ...] = ("a", "b")) -> Lane:
    return Lane(name, addresses, wall, tuple(10.0 * (index + 1) for index in range(len(addresses))))


def test_report_requires_equal_completed_sets_and_calculates_k_star(tmp_path: Path) -> None:
    payload = report("tiny", [lane("export", 10), lane("parallel", 5), lane("native-console", 3)], options_sha256="a" * 64, timeout_s=60)
    assert payload["k_star"] == 5.0
    json_path, md_path = write_report(tmp_path, payload)
    assert json_path.is_file() and "native-console" in md_path.read_text()


def test_report_refuses_completion_drift() -> None:
    with pytest.raises(CompletionMismatch, match="REFUSED"):
        report("tiny", [lane("serial", 3), lane("native-batch", 2, ("a",))], options_sha256="x", timeout_s=60)


def test_k_star_is_never_without_native_advantage() -> None:
    assert report("tiny", [lane("export", 1), lane("parallel", 2), lane("native-batch", 2)], options_sha256="x", timeout_s=60)["k_star"] == "never"


def test_verify_corpus_rejects_hash_drift(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    fixture = tmp_path / "tests" / "a"
    fixture.write_text("correct")
    digest = __import__("hashlib").sha256(b"correct").hexdigest()
    manifest = tmp_path / "corpora.json"
    manifest.write_text('{"schema":"agentdecompile.native-bench-corpora/v0","corpora":{"tiny":{"sha256":{"tests/a":"' + digest + '"}}}}')
    assert verify_corpus(manifest, "tiny", repo_root=tmp_path)["sha256"]
    fixture.write_text("drift")
    with pytest.raises(CorpusMismatch, match="hash mismatch"):
        verify_corpus(manifest, "tiny", repo_root=tmp_path)
