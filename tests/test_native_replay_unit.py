from pathlib import Path
import subprocess

from agentdecompile_recovery.native_snapshot.manifest import FunctionEntry, STATUS_OK
from agentdecompile_recovery.native_snapshot.replay import BatchReplayer, ConsoleReplayer, _extract, _script


def entry() -> FunctionEntry:
    return FunctionEntry(addr="0000000000401000", space="ram", name="add", load_name="add", size=1, status=STATUS_OK, savefile="functions/add.xml")


def test_script_has_console_commands_and_marker_extraction(tmp_path: Path):
    script = _script(tmp_path / "a.xml", "add", "__MARK__")
    assert "restore " in script and "load function add" in script and "print C" in script
    assert _extract("noise\n__MARK__:BEGIN\nint add(void) {}\n__MARK__:END\n", "__MARK__") == "int add(void) {}\n"
    assert _extract("no markers", "__MARK__") is None


def test_replayer_uses_fresh_console_process(monkeypatch, tmp_path: Path):
    path = tmp_path / "functions" / "add.xml"
    path.parent.mkdir()
    path.write_text("<xml_savefile/>")
    seen: dict[str, object] = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["input"] = kwargs["input"]
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args, 0, "__GNSDK_REPLAY_0000000000401000__:BEGIN\nint add(void) {}\n__GNSDK_REPLAY_0000000000401000__:END\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ConsoleReplayer(Path("/fake/console"), sleigh_home=Path("/fake/sleigh")).replay(tmp_path, entry())
    assert seen["args"] == ["/fake/console"]
    assert seen["env"]["SLEIGHHOME"] == "/fake/sleigh"
    assert seen["input"]
    assert "load function add" in str(seen["input"])
    assert result.c_text == "int add(void) {}\n" and result.returncode == 0


def test_batch_replayer_parses_snapshot_jsonl(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["timeout"] = kwargs["timeout"]
        output = Path(args[args.index("--output") + 1])
        output.write_text(
            '{"id":"0000000000401000","status":"ok","result":{"name":"add","c":"int add(void) {}\\n"}}\n',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = BatchReplayer(
        Path("/fake/gnsdk-batch"),
        sleigh_home=Path("/fake/sleigh"),
        timeout_s=30,
        workers=2,
        tmpdir=tmp_path / "tmp",
    ).replay_manifest(tmp_path, object())
    assert seen["args"][:5] == ["/fake/gnsdk-batch", "--sleigh-home", "/fake/sleigh", "--snapshot", str(tmp_path)]
    assert "--workers" in seen["args"] and seen["args"][seen["args"].index("--workers") + 1] == "2"
    assert "--tmpdir" in seen["args"]
    assert seen["timeout"] == 40
    assert result["0000000000401000"].c_text == "int add(void) {}\n"
