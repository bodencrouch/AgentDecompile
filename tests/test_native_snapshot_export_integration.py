"""Integration tests: export a real snapshot of ``tests/fixtures/test_x86_64`` through PyGhidra."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import warnings

import pytest

from agentdecompile_recovery.native_snapshot import manifest as m
from agentdecompile_recovery.native_snapshot.exporter import (
    ProgressEvent,
    SnapshotPreconditionError,
    SnapshotStaleError,
    UnsupportedStyleError,
    export_snapshot,
    resolve_functions,
)

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent / "fixtures" / "test_x86_64"


def _ghidra_available() -> bool:
    install = os.environ.get("GHIDRA_INSTALL_DIR", "").strip()
    if not install or not (Path(install) / "Ghidra" / "application.properties").is_file():
        return False
    try:
        import pyghidra  # noqa: F401
    except ImportError:
        return False
    return True


needs_ghidra = pytest.mark.skipif(not _ghidra_available(), reason="GHIDRA_INSTALL_DIR not set to a Ghidra install or pyghidra missing")


@pytest.fixture(scope="module")
def analyzed_program(ghidra_initialized, tmp_path_factory: pytest.TempPathFactory):
    import pyghidra

    project_dir = tmp_path_factory.mktemp("native_snapshot_project")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        context = pyghidra.open_program(str(FIXTURE), project_location=str(project_dir), project_name="native_snapshot", analyze=True)
    with context as flat_api:
        program = flat_api.getCurrentProgram()
        # PyGhidra leaves a historical ``Batch Processing`` transaction info
        # record after import/analysis.  The exporter recognises that exact
        # stale shape while still rejecting a transaction created by a caller.
        assert program.getCurrentTransactionInfo() is not None
        yield program


@pytest.fixture(scope="module")
def exported(analyzed_program, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, m.Manifest, list[ProgressEvent], int]:
    out = tmp_path_factory.mktemp("native_snapshot_out")
    events: list[ProgressEvent] = []
    mod_before = int(analyzed_program.getModificationNumber())
    manifest = export_snapshot(analyzed_program, out, timeout_s=60, on_progress=events.append)
    return out, manifest, events, mod_before


@needs_ghidra
def test_export_writes_savefiles_with_expected_structure(exported) -> None:
    out, manifest, _events, _mod_before = exported
    ok_entries = manifest.ok_entries()
    assert ok_entries, "expected at least one ok function in the fixture"
    for entry in ok_entries:
        assert entry.savefile is not None
        savefile = out / entry.savefile
        assert savefile.is_file()
        text = savefile.read_text(encoding="utf-8", errors="replace")
        assert text.startswith("<xml_savefile"), text[:80]
        first_line_end = text.index("\n")
        header = text[:first_line_end]
        assert f'name="{entry.name}"' in header
        assert 'target="default"' in header
        rest = text[first_line_end + 1 :]
        assert rest.startswith("<binaryimage"), rest[:80]
        image_end = rest.index("</binaryimage>")
        after_image = rest[image_end + len("</binaryimage>") :].lstrip()
        assert after_image.startswith(("<coretypes>", "<specextensions>")), after_image[:80]
        assert "<save_state>" in text
        assert text.rstrip().endswith("</xml_savefile>")
        assert entry.sha256 == hashlib.sha256(savefile.read_bytes()).hexdigest()
        assert not m.is_partial_name(savefile.name)


@needs_ghidra
def test_export_oracle_c_and_json(exported) -> None:
    out, manifest, _events, _mod_before = exported
    for entry in manifest.ok_entries():
        assert entry.oracle_c and entry.oracle_json
        c_text = (out / entry.oracle_c).read_text(encoding="utf-8")
        assert c_text.strip()
        assert entry.java_c_sha256 == hashlib.sha256(c_text.encode("utf-8")).hexdigest()
        record = json.loads((out / entry.oracle_json).read_text(encoding="utf-8"))
        assert record["status"] == m.STATUS_OK
        assert record["addr"] == entry.addr
        assert record["c_sha256"] == entry.java_c_sha256
        assert record["decompile_ms"] == entry.decompile_ms
        assert isinstance(record["warnings"], list)
        assert record["signature"]


@needs_ghidra
def test_export_manifest_validates_and_round_trips(exported) -> None:
    out, manifest, events, mod_before = exported
    data = manifest.to_dict()
    assert m.validate_manifest(data) == [], m.validate_manifest(data)
    loaded = m.load_manifest(out)
    assert loaded == manifest
    assert manifest.schema == m.SCHEMA
    assert manifest.export_requires_java_decompile is True
    assert manifest.producer.ghidra_version
    assert manifest.producer.exporter_version == m.EXPORTER_VERSION
    assert manifest.program.language_id.startswith("x86:LE:64")
    assert manifest.program.name
    assert manifest.engine.sla_format_version == 4
    assert manifest.engine.sig_major > 0
    assert manifest.program.language_id in manifest.engine.java_sla_sha256
    assert manifest.capabilities.supported is True
    assert manifest.capabilities.supports == ["decompile-c"]
    assert manifest.capabilities.unsupported_languages == ["JVM", "Dalvik"]
    assert manifest.options.simplification_style == "decompile"
    assert manifest.total_bytes > 0
    assert manifest.counts.total == len(manifest.functions) == len(events)
    assert manifest.counts.ok >= 3
    names = {e.name for e in manifest.ok_entries()}
    assert {"_add", "_multiply", "entry"} <= names, names
    assert manifest.revision.stale is False
    assert manifest.revision.modification_number_before == mod_before
    assert manifest.revision.modification_number_after == mod_before
    assert all(ev.status in m.STATUSES for ev in events)
    assert [ev.index for ev in events] == list(range(1, len(events) + 1))


@needs_ghidra
def test_export_options_xml_matches_savefile_embedding(exported) -> None:
    out, manifest, _events, _mod_before = exported
    options_path = out / manifest.options.path
    options_bytes = options_path.read_bytes()
    assert options_bytes.lstrip().startswith(b"<optionslist")
    assert manifest.options.sha256 == hashlib.sha256(options_bytes).hexdigest()
    entry = manifest.ok_entries()[0]
    savefile_bytes = (out / entry.savefile).read_bytes()
    assert options_bytes in savefile_bytes


@needs_ghidra
def test_export_leaves_modification_number_unchanged(exported, analyzed_program) -> None:
    _out, manifest, _events, mod_before = exported
    assert int(analyzed_program.getModificationNumber()) == mod_before == manifest.revision.modification_number_before
    from agentdecompile_recovery.native_snapshot.exporter import _has_open_transaction
    assert not _has_open_transaction(analyzed_program)


@needs_ghidra
def test_export_selected_functions_by_address(exported, analyzed_program, tmp_path: Path) -> None:
    _out, manifest, _events, _mod_before = exported
    add_entry = next(e for e in manifest.ok_entries() if e.name == "_add")
    functions = resolve_functions(analyzed_program, [int(add_entry.addr, 16), f"ram:{add_entry.addr}"])
    assert len(functions) == 1
    assert str(functions[0].getName()) == "_add"
    subset = export_snapshot(analyzed_program, tmp_path / "subset", functions=functions, timeout_s=60)
    assert subset.counts.total == 1
    assert subset.counts.ok == 1
    assert subset.functions[0].addr == add_entry.addr
    assert subset.functions[0].java_c_sha256 == add_entry.java_c_sha256
    assert subset.options.sha256 == manifest.options.sha256
    with pytest.raises(ValueError, match="no function at"):
        resolve_functions(analyzed_program, [0])


@needs_ghidra
def test_export_refuses_open_transaction(analyzed_program, tmp_path: Path) -> None:
    tx = analyzed_program.startTransaction("native-snapshot-test")
    try:
        with pytest.raises(SnapshotPreconditionError, match="open transaction"):
            export_snapshot(analyzed_program, tmp_path / "refused", timeout_s=60)
    finally:
        analyzed_program.endTransaction(tx, False)
    from agentdecompile_recovery.native_snapshot.exporter import _has_open_transaction
    assert not _has_open_transaction(analyzed_program)
    assert not (tmp_path / "refused" / m.MANIFEST_FILENAME).exists()


@needs_ghidra
def test_export_refuses_non_decompile_style(analyzed_program, tmp_path: Path) -> None:
    from agentdecompile_cli.mcp_utils.decompiler_util import _configure_decompiler_for_program

    def normalize_configurer(ifc, program) -> None:
        _configure_decompiler_for_program(ifc, program)
        ifc.setSimplificationStyle("normalize")

    with pytest.raises(UnsupportedStyleError, match="normalize"):
        export_snapshot(analyzed_program, tmp_path / "style", timeout_s=60, configurer=normalize_configurer)


@needs_ghidra
def test_export_flags_stale_program(analyzed_program, tmp_path: Path) -> None:
    """A mutation during export marks revision.stale; without allow_stale the manifest is still written and the call raises."""
    functions = list(analyzed_program.getFunctionManager().getFunctions(True))[:2]
    assert len(functions) == 2
    bumped = False
    mutation_number = 0

    def mutate_once(event: ProgressEvent) -> None:
        nonlocal bumped, mutation_number
        if bumped:
            return
        bumped = True
        mutation_number += 1
        tx = analyzed_program.startTransaction("native-snapshot-stale")
        try:
            analyzed_program.getBookmarkManager().setBookmark(functions[0].getEntryPoint(), "Note", "native-snapshot", f"stale test {mutation_number}")
        finally:
            analyzed_program.endTransaction(tx, True)

    out = tmp_path / "stale"
    with pytest.raises(SnapshotStaleError) as excinfo:
        export_snapshot(analyzed_program, out, functions=functions, timeout_s=60, on_progress=mutate_once)
    manifest = excinfo.value.manifest
    assert manifest.revision.stale is True
    assert manifest.revision.modification_number_after != manifest.revision.modification_number_before
    assert manifest.counts.total == 1, "export stops at the first observed change"
    on_disk = json.loads((out / m.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert on_disk["revision"]["stale"] is True
    assert m.validate_manifest(on_disk) == []

    bumped = False
    tolerated = export_snapshot(analyzed_program, tmp_path / "stale-allowed", functions=functions, timeout_s=60, on_progress=mutate_once, allow_stale=True)
    assert tolerated.revision.stale is True
    assert tolerated.counts.total == 2
