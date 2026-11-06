from agentdecompile_recovery.native_snapshot.canonical import canonicalize, layout_collapsed


def test_canonicalize_is_narrow_and_idempotent() -> None:
    source = "int x;  \r\n\r\n\t\r\n"
    assert canonicalize(source) == "int x;\n"
    assert canonicalize(canonicalize(source)) == "int x;\n"


def test_layout_collapse_is_diagnostic_only() -> None:
    assert canonicalize("int x = 1;\n") != canonicalize("int   x = 1;\n")
    assert layout_collapsed("int x = 1;\n") == layout_collapsed("int   x = 1;\n")
