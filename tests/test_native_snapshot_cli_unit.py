import argparse
import json

from agentdecompile_recovery.native_snapshot import cli
from agentdecompile_recovery.native_snapshot.cli import build_parser
from agentdecompile_recovery.native_snapshot.manifest import (
    Capabilities,
    Counts,
    EngineInfo,
    FunctionEntry,
    Manifest,
    OptionsInfo,
    Producer,
    ProgramInfo,
    Revision,
    STATUS_OK,
)
from agentdecompile_recovery.native_snapshot.replay import ReplayResult


def test_diff_subcommand_requires_native_inputs():
    parser = build_parser()
    args = parser.parse_args(["diff", "snapshot", "--console", "console", "--sleigh-home", "sleigh"])
    assert args.command == "diff"
    assert args.mode == "console"
    assert args.timeout_s == 60
    assert args.output is None


def test_replay_subcommand_accepts_batch_backend():
    parser = build_parser()
    args = parser.parse_args([
        "replay",
        "snapshot",
        "--mode",
        "batch",
        "--batch",
        "gnsdk-batch",
        "--sleigh-home",
        "sleigh",
        "--workers",
        "2",
        "--tmpdir",
        "tmp",
    ])
    assert args.command == "replay"
    assert args.mode == "batch"
    assert args.workers == 2
    assert args.per_process == 200
    assert str(args.tmpdir) == "tmp"


def test_console_diff_fails_strict_parity_without_engine_metadata(monkeypatch, tmp_path):
    (tmp_path / "oracle").mkdir()
    (tmp_path / "oracle/add.c").write_text("int add(void) {}\n")
    entry = FunctionEntry(
        addr="0000000000401000", space="ram", name="add", load_name="add", size=1,
        status=STATUS_OK, oracle_c="oracle/add.c",
    )
    manifest = Manifest(
        schema="agentdecompile.native-snapshot/v0", export_requires_java_decompile=True,
        created_at="now", timeout_s=1, wall_s=0,
        producer=Producer("12.1.3", "x", "x"),
        program=ProgramInfo("x", "x86:LE:64:default", "default", "0x0"),
        engine=EngineInfo(1, 1), options=OptionsInfo("x" * 64, "options.xml", "decompile"),
        capabilities=Capabilities(True, ["decompile-c"], ["JVM"], []),
        revision=Revision(0, 0, False), counts=Counts(total=1, ok=1), total_bytes=0,
        functions=[entry],
    )

    class Replayer:
        def replay_manifest(self, root, loaded):
            assert root == tmp_path and loaded is manifest
            return {
                entry.stable_id: ReplayResult(
                    entry.addr, entry.name, "int add(void) {}\n", "", 0, space=entry.space
                )
            }

    monkeypatch.setattr(cli, "_load_snapshot", lambda snapshot: manifest)
    monkeypatch.setattr(cli, "_make_replayer", lambda args: Replayer())
    args = argparse.Namespace(snapshot=tmp_path, mode="console", output=None)
    assert cli.run_diff(args) == 1
    report = json.loads((tmp_path / "differential/report.json").read_text())
    assert report["parity"] == {
        "ok": False,
        "errors": ["native replay did not report engine metadata"],
        "warnings": [],
    }
