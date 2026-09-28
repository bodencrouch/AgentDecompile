from pathlib import Path
import subprocess
import sys

import pytest

from agentdecompile_recovery.native_snapshot.bench import CompletionMismatch, CorpusMismatch, Lane, report, verify_corpus, write_report


def lane(name: str, wall: float, addresses: tuple[str, ...] = ("a", "b")) -> Lane:
    return Lane(name, addresses, wall, tuple(10.0 * (index + 1) for index in range(len(addresses))))


def test_report_requires_equal_completed_sets_and_calculates_k_star(tmp_path: Path) -> None:
    payload = report("tiny", [lane("export", 10), lane("parallel-4", 6), lane("parallel-8", 5), lane("native-console", 3)], options_sha256="a" * 64, timeout_s=60)
    assert payload["best_java_lane"] == "parallel-8"
    assert payload["best_native_lane"] == "native-console"
    assert payload["held_constant"]["function_count"] == 2
    assert payload["k_star"] == 5.0
    json_path, md_path = write_report(tmp_path, payload)
    rendered = md_path.read_text()
    assert json_path.is_file() and "native-console" in rendered and "## Held constant" in rendered


def test_report_records_resource_metrics() -> None:
    payload = report(
        "tiny",
        [
            Lane("serial", ("a",), 2, (10.0,), cpu_s=1.5, rss_hwm_mb=256.0, jvm_heap_max_mb=128.0, child_hwm=1, named_child_hwm=1),
            Lane("native-batch", ("a",), 1, (8.0,), cpu_s=0.75, rss_hwm_mb=16.0, child_hwm=0, named_child_hwm=0),
        ],
        options_sha256="x",
        timeout_s=60,
    )
    serial = payload["lanes"][0]
    assert serial["cpu_s"] == 1.5
    assert serial["rss_hwm_mb"] == 256.0
    assert serial["jvm_heap_max_mb"] == 128.0
    assert serial["child_hwm"] == 1
    assert serial["named_child_hwm"] == 1


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


def test_bench_script_refuses_completion_drift(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        json_manifest(
            addresses=("a", "b"),
            options_sha256="a" * 64,
        ),
        encoding="utf-8",
    )
    lanes = tmp_path / "lanes.jsonl"
    lanes.write_text(
        "\n".join(
            [
                '{"name":"serial","completed":["a","b"],"wall_s":2.0,"elapsed_ms":[1.0,1.0]}',
                '{"name":"native-batch","completed":["a"],"wall_s":1.0,"elapsed_ms":[1.0]}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/bench_native_sdk.py",
            "--snapshot",
            str(snapshot),
            "--output",
            str(tmp_path / "out"),
            "--lane-jsonl",
            str(lanes),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 3
    assert "REFUSED (completion mismatch)" in completed.stderr


def json_manifest(*, addresses: tuple[str, ...], options_sha256: str) -> str:
    concrete = tuple(f"{index + 1:016x}" for index, _addr in enumerate(addresses))
    functions = [
        {
            "addr": addr,
            "space": "ram",
            "name": f"fn_{addr}",
            "load_name": f"fn_{addr}",
            "size": 1,
            "status": "ok",
            "savefile": f"functions/{addr}.xml",
            "sha256": "0" * 64,
            "decompile_ms": 1,
            "java_c_sha256": "0" * 64,
            "oracle_c": f"oracle/{addr}.c",
            "oracle_json": f"oracle/{addr}.json",
            "signature": "void x(void)",
            "warnings": [],
            "error": None,
            "skip_reason": None,
            "overlay": False,
            "load_mode": "function",
        }
        for addr in concrete
    ]
    return __import__("json").dumps(
        {
            "schema": "agentdecompile.native-snapshot/v0",
            "export_requires_java_decompile": True,
            "created_at": "2026-09-10T00:00:00Z",
            "timeout_s": 60,
            "wall_s": 1.0,
            "producer": {"ghidra_version": "12.1.3", "pyghidra_version": "3.0.2", "jpype_version": "1.5.2", "exporter_version": "0.1.0", "host": {"platform": "test", "node": "test", "python": "3.14", "java": "21"}},
            "binary": {"path": "test", "sha256": "0" * 64, "size": 1},
            "program": {"name": "test", "language_id": "x86:LE:64:default", "compiler_spec_id": "gcc", "image_base": "0", "executable_path": "test", "md5": "0" * 32, "sha256": "0" * 64, "metadata": {}},
            "engine": {"sig_major": 6, "sig_minor": 1, "sla_format_version": 4, "java_sla_sha256": {"x86:LE:64:default": "1" * 64}, "respawns": 0},
            "options": {"sha256": options_sha256, "simplification_style": "decompile", "path": "options.xml"},
            "capabilities": {"supports": ["decompile-c"], "unsupported_languages": ["JVM", "Dalvik"], "supported": True, "overlay_spaces": []},
            "revision": {"modification_number_before": 1, "modification_number_after": 1, "stale": False},
            "counts": {"total": len(functions), "ok": len(functions), "timed_out": 0, "error": 0, "skipped": 0, "skipped_by_reason": {}},
            "total_bytes": 0,
            "functions": functions,
        }
    )
