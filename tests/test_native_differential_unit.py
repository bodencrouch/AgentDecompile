from pathlib import Path

from agentdecompile_recovery.native_snapshot.differential import (
    MATCH,
    MISMATCH_CONTENT,
    MISMATCH_LAYOUT,
    NATIVE_CRASH,
    NATIVE_ERROR,
    ORACLE_ABSENT,
    classify,
    write_report,
)
from agentdecompile_recovery.native_snapshot.manifest import Capabilities, Counts, EngineInfo, Manifest, OptionsInfo, Producer, ProgramInfo, Revision
from agentdecompile_recovery.native_snapshot.manifest import FunctionEntry, STATUS_OK


def entry() -> FunctionEntry:
    return FunctionEntry(addr="0000000000401000", space="ram", name="add", load_name="add", size=1, status=STATUS_OK, oracle_c="oracle/add.c")


def test_exact_canonical_match_and_strict_layout_label(tmp_path: Path) -> None:
    (tmp_path / "oracle").mkdir()
    (tmp_path / "oracle/add.c").write_text("int add(void) { return 1; }  \r\n")
    assert classify(entry(), tmp_path, "int add(void) { return 1; }\n").classification == MATCH
    assert classify(entry(), tmp_path, "int  add(void) { return 1; }\n").classification == MISMATCH_LAYOUT
    assert classify(entry(), tmp_path, "int add(void) { return 2; }\n").classification == MISMATCH_CONTENT
    assert classify(entry(), tmp_path, None, crashed=True).classification == NATIVE_CRASH
    assert classify(entry(), tmp_path, None).classification == NATIVE_ERROR
    missing = FunctionEntry(addr="1", space="ram", name="missing", load_name="missing", size=1, status=STATUS_OK)
    assert classify(missing, tmp_path, None).classification == ORACLE_ABSENT


def test_report_writes_native_text_without_overwriting_oracle(tmp_path: Path) -> None:
    (tmp_path / "oracle").mkdir()
    (tmp_path / "oracle/add.c").write_text("int add(void) { return 1; }\n")
    manifest = Manifest(schema="agentdecompile.native-snapshot/v0", export_requires_java_decompile=True, created_at="now", timeout_s=1, wall_s=0,
        producer=Producer("12.1.3", "x", "x"), program=ProgramInfo("x", "x86:LE:64:default", "default", "0x0"), engine=EngineInfo(1, 1),
        options=OptionsInfo("x" * 64, "options.xml", "decompile"), capabilities=Capabilities(True, ["decompile-c"], ["JVM"], []),
        revision=Revision(0, 0, False), counts=Counts(total=1, ok=1), total_bytes=0, functions=[entry()])
    results = write_report(tmp_path, manifest, {entry().addr: "int add(void) { return 1; }\n"})
    assert results[0].classification == MATCH
    assert (tmp_path / "differential" / "native" / "0000000000401000.c").is_file()
    assert (tmp_path / "differential" / "report.json").is_file()
    assert (tmp_path / "differential" / "report.md").is_file()


def test_report_writes_content_diff(tmp_path: Path) -> None:
    (tmp_path / "oracle").mkdir()
    (tmp_path / "oracle/add.c").write_text("int add(void) { return 1; }\n")
    manifest = Manifest(schema="agentdecompile.native-snapshot/v0", export_requires_java_decompile=True, created_at="now", timeout_s=1, wall_s=0,
        producer=Producer("12.1.3", "x", "x"), program=ProgramInfo("x", "x86:LE:64:default", "default", "0x0"), engine=EngineInfo(1, 1),
        options=OptionsInfo("x" * 64, "options.xml", "decompile"), capabilities=Capabilities(True, ["decompile-c"], ["JVM"], []),
        revision=Revision(0, 0, False), counts=Counts(total=1, ok=1), total_bytes=0, functions=[entry()])
    results = write_report(tmp_path, manifest, {entry().addr: "int add(void) { return 2; }\n"})
    assert results[0].classification == MISMATCH_CONTENT
    assert results[0].diff_path == "differential/diff/0000000000401000.diff"
    assert (tmp_path / results[0].diff_path).read_text(encoding="utf-8").startswith("--- java-oracle")
