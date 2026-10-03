from pathlib import Path
import subprocess

from agentdecompile_recovery.native_snapshot.manifest import Capabilities, Counts, EngineInfo, FunctionEntry, Manifest, OptionsInfo, Producer, ProgramInfo, Revision, STATUS_OK
from agentdecompile_recovery.native_snapshot.replay import BatchReplayer, ConsoleReplayer, _extract, _native_sla_hashes, _script, batch_process_timeout_s


def entry() -> FunctionEntry:
    return FunctionEntry(addr="0000000000401000", space="ram", name="add", load_name="add", size=1, status=STATUS_OK, savefile="functions/add.xml")


def manifest(*entries: FunctionEntry) -> Manifest:
    return Manifest(schema="agentdecompile.native-snapshot/v0", export_requires_java_decompile=True, created_at="now", timeout_s=1, wall_s=0,
        producer=Producer("12.1.3", "x", "x"), program=ProgramInfo("x", "x86:LE:64:default", "default", "0x0"), engine=EngineInfo(6, 1),
        options=OptionsInfo("x" * 64, "options.xml", "decompile"), capabilities=Capabilities(True, ["decompile-c"], ["JVM"], []),
        revision=Revision(0, 0, False), counts=Counts(total=len(entries), ok=len(entries)), total_bytes=0, functions=list(entries))


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
        return subprocess.CompletedProcess(args, 0, "__GNSDK_REPLAY_ram__0000000000401000__:BEGIN\nint add(void) {}\n__GNSDK_REPLAY_ram__0000000000401000__:END\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ConsoleReplayer(Path("/fake/console"), sleigh_home=Path("/fake/sleigh")).replay(tmp_path, entry())
    assert seen["args"] == ["/fake/console"]
    assert seen["env"]["SLEIGHHOME"] == "/fake/sleigh"
    assert seen["input"]
    assert "load function add" in str(seen["input"])
    assert result.c_text == "int add(void) {}\n" and result.returncode == 0


def test_console_replay_manifest_reuses_process_per_chunk(monkeypatch, tmp_path: Path):
    entries = [
        entry(),
        FunctionEntry(addr="0000000000401001", space="ram", name="sub", load_name="sub", size=1, status=STATUS_OK, savefile="functions/sub.xml"),
    ]
    for item in entries:
        path = tmp_path / item.savefile
        path.parent.mkdir(exist_ok=True)
        path.write_text("<xml_savefile/>")
    calls: list[str] = []

    def fake_run(args, **kwargs):
        calls.append(kwargs["input"])
        stdout = (
            "__GNSDK_REPLAY_ram__0000000000401000__:BEGIN\nint add(void) {}\n__GNSDK_REPLAY_ram__0000000000401000__:END\n"
            "__GNSDK_REPLAY_ram__0000000000401001__:BEGIN\nint sub(void) {}\n__GNSDK_REPLAY_ram__0000000000401001__:END\n"
        )
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ConsoleReplayer(Path("/fake/console"), sleigh_home=Path("/fake/sleigh"), per_process=200).replay_manifest(tmp_path, manifest(*entries))
    assert len(calls) == 1
    assert calls[0].count("restore ") == 2
    assert calls[0].rstrip().endswith("quit")
    assert result["ram:0000000000401000"].c_text == "int add(void) {}\n"
    assert result["ram:0000000000401001"].c_text == "int sub(void) {}\n"


def test_console_replay_keeps_same_offset_spaces_distinct(monkeypatch, tmp_path: Path) -> None:
    entries = [
        FunctionEntry(addr="0000000000002000", space="ram", name="base", load_name="base", size=1, status=STATUS_OK, savefile="functions/base.xml"),
        FunctionEntry(addr="0000000000002000", space="ovl0", name="overlay", load_name="overlay", size=1, status=STATUS_OK, savefile="functions/overlay.xml", overlay=True),
    ]
    for item in entries:
        path = tmp_path / item.savefile
        path.parent.mkdir(exist_ok=True)
        path.write_text("<xml_savefile/>")

    def fake_run(args, **kwargs):
        stdout = (
            "__GNSDK_REPLAY_ram__0000000000002000__:BEGIN\nint base(void) {}\n__GNSDK_REPLAY_ram__0000000000002000__:END\n"
            "__GNSDK_REPLAY_ovl0__0000000000002000__:BEGIN\nint overlay(void) {}\n__GNSDK_REPLAY_ovl0__0000000000002000__:END\n"
        )
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ConsoleReplayer(Path("/fake/console")).replay_manifest(tmp_path, manifest(*entries))
    assert result["ram:0000000000002000"].c_text == "int base(void) {}\n"
    assert result["ovl0:0000000000002000"].c_text == "int overlay(void) {}\n"


def test_batch_replayer_parses_snapshot_jsonl(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["timeout"] = kwargs["timeout"]
        output = Path(args[args.index("--output") + 1])
        output.write_text(
            '{"id":"ram:0000000000401000","status":"ok","engines":[{"source":"Ghidra_12.1.3_build","abi":"0.1.0","sig_major":6,"sig_minor":1}],"result":{"name":"add","c":"int add(void) {}\\n"}}\n',
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
    ).replay_manifest(tmp_path, manifest(entry()))
    assert seen["args"][:5] == ["/fake/gnsdk-batch", "--sleigh-home", "/fake/sleigh", "--snapshot", str(tmp_path)]
    assert "--workers" in seen["args"] and seen["args"][seen["args"].index("--workers") + 1] == "2"
    assert "--tmpdir" in seen["args"]
    assert seen["timeout"] == 100
    assert result["ram:0000000000401000"].c_text == "int add(void) {}\n"
    assert result["ram:0000000000401000"].engines == ({"source": "Ghidra_12.1.3_build", "abi": "0.1.0", "sig_major": 6, "sig_minor": 1, "sla_sha256": {}},)


def test_batch_process_timeout_scales_by_two_operations_and_worker_waves() -> None:
    assert batch_process_timeout_s(0, 4, 60) == 40
    assert batch_process_timeout_s(5, 2, 30) == 220
    assert batch_process_timeout_s(50, 1, 2) == 240


def test_native_sla_hashes_reads_language_definitions(tmp_path: Path) -> None:
    languages = tmp_path / "Ghidra" / "Processors" / "x86" / "data" / "languages"
    languages.mkdir(parents=True)
    (languages / "x86.ldefs").write_text(
        '<language_definitions><language id="x86:LE:64:default" slafile="x86-64.sla"/></language_definitions>',
        encoding="utf-8",
    )
    (languages / "x86-64.sla").write_bytes(b"sla")
    assert _native_sla_hashes(tmp_path, {"x86:LE:64:default"}) == {
        "x86:LE:64:default": "9dfbc63747c6ec4e8d43b376ea383efc51c41e08d7de1901151db85e1b487784"
    }
