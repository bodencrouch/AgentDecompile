from pathlib import Path

from agentdecompile_recovery.native_snapshot.differential import MATCH, MISMATCH_CONTENT, MISMATCH_LAYOUT, NATIVE_CRASH, classify
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
