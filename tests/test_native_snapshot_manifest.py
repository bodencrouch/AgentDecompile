"""Unit tests for the native snapshot manifest schema (no Ghidra, no JVM)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from agentdecompile_recovery.native_snapshot import manifest as m
from agentdecompile_recovery.native_snapshot.exporter import normalize_savefile_for_native_restore
from agentdecompile_recovery.native_snapshot.exporter import _has_open_transaction

pytestmark = pytest.mark.unit


def _entry(addr: int, status: str = m.STATUS_OK, **overrides) -> m.FunctionEntry:
    savefile = m.savefile_name("ram", addr, False)
    stem = m.savefile_stem(savefile)
    fields = {
        "addr": m.addr16(addr),
        "space": "ram",
        "name": f"FUN_{addr:08x}",
        "load_name": f"FUN_{addr:08x}",
        "size": 32,
        "status": status,
        "savefile": f"functions/{savefile}",
        "sha256": "a" * 64,
        "decompile_ms": 12,
        "java_c_sha256": "b" * 64,
        "oracle_c": f"oracle/{stem}.c",
        "oracle_json": f"oracle/{stem}.json",
    }
    if status == m.STATUS_TIMED_OUT:
        fields.update(savefile=f"functions/{m.partial_name(savefile)}", sha256=None, java_c_sha256=None, oracle_c=None, error="timed out")
    elif status == m.STATUS_ERROR:
        fields.update(savefile=None, sha256=None, java_c_sha256=None, oracle_c=None, error="boom")
    elif status == m.STATUS_SKIPPED:
        fields.update(savefile=None, sha256=None, java_c_sha256=None, oracle_c=None, oracle_json=None, decompile_ms=None, skip_reason=m.SKIP_THUNK)
    fields.update(overrides)
    return m.FunctionEntry(**fields)


def _manifest(entries: list[m.FunctionEntry] | None = None, *, stale: bool = False) -> m.Manifest:
    entries = entries if entries is not None else [_entry(0x401000), _entry(0x401040, m.STATUS_TIMED_OUT), _entry(0x401080, m.STATUS_SKIPPED)]
    manifest = m.Manifest(
        producer=m.Producer(ghidra_version="12.1.3", pyghidra_version="3.0.2", jpype_version="1.5.2", host={"platform": "test"}),
        program=m.ProgramInfo(name="fixture", language_id="x86:LE:64:default", compiler_spec_id="gcc", image_base="00100000", executable_path="/tmp/fixture", md5="0" * 32, sha256="0" * 64, metadata={"Executable Format": "ELF"}),
        engine=m.EngineInfo(sig_major=6, sig_minor=1, java_sla_sha256={"x86:LE:64:default": "c" * 64}, respawns=0),
        options=m.OptionsInfo(sha256="d" * 64),
        capabilities=m.Capabilities(supported=True, overlay_spaces=[]),
        revision=m.Revision(modification_number_before=7, modification_number_after=8 if stale else 7, stale=stale),
        functions=entries,
        total_bytes=1234,
        timeout_s=60,
        created_at="2026-09-09T00:00:00+00:00",
        wall_s=1.5,
    )
    manifest.recount()
    return manifest


def test_schema_constants() -> None:
    assert m.SCHEMA == "agentdecompile.native-snapshot/v0"
    assert m.EXPORTER_VERSION == "0.1.0"
    assert m.SLA_FORMAT_VERSION == 4
    assert "decompile-c" in m.SUPPORTED_CAPABILITIES
    assert m.UNSUPPORTED_LANGUAGES == ("JVM", "Dalvik")


def test_savefile_name_plain_and_overlay() -> None:
    assert m.savefile_name("ram", 0x401000, False) == "0000000000401000.xml"
    assert m.savefile_name("ram", 0x100000470, False) == "0000000100000470.xml"
    assert m.savefile_name("ovl0", 0x401000, True) == "ovl0__0000000000401000.xml"
    assert m.savefile_name("my overlay:1", 0x10, True) == "my_overlay_1__0000000000000010.xml"
    assert m.savefile_name("ram", 0xFFFFFFFFFFFFFFFF, False) == "ffffffffffffffff.xml"
    with pytest.raises(ValueError, match="negative"):
        m.savefile_name("ram", -1, False)


def test_partial_name_and_stem() -> None:
    assert m.partial_name("0000000000401000.xml") == "0000000000401000.partial.xml"
    assert m.partial_name("ovl__0000000000401000.xml") == "ovl__0000000000401000.partial.xml"
    assert m.partial_name("0000000000401000.partial.xml") == "0000000000401000.partial.xml"
    assert m.is_partial_name("x.partial.xml") and not m.is_partial_name("x.xml")
    assert m.savefile_stem("0000000000401000.partial.xml") == "0000000000401000"
    assert m.oracle_names("ovl__0000000000401000.xml") == ("oracle/ovl__0000000000401000.c", "oracle/ovl__0000000000401000.json")


def test_savefile_normalizer_moves_undefined_type_before_forward_reference() -> None:
    text = """<xml_savefile>
<typegrp>
  <type name="" metatype="ptr" size="8">
    <typeref name="undefined" id="0xc000000000000000"/>
  </type>
  <type name="undefined" id="0xc000000000000000" metatype="unknown" size="1"/>
  <type name="undefined1" size="1" metatype="unknown" id="0xc0000000000000b4"/>
</typegrp>
</xml_savefile>
"""
    normalized = normalize_savefile_for_native_restore(text)
    assert normalized.index('<type name="undefined" id="0xc000000000000000"') < normalized.index('<typeref name="undefined"')
    assert normalized.count('id="0xc000000000000000"') == 2


def test_round_trip_to_dict_from_dict() -> None:
    manifest = _manifest()
    data = manifest.to_dict()
    assert data["schema"] == m.SCHEMA
    assert data["export_requires_java_decompile"] is True
    assert list(data)[:2] == ["schema", "export_requires_java_decompile"]
    restored = m.Manifest.from_dict(json.loads(json.dumps(data)))
    assert restored == manifest
    assert restored.to_dict() == data


def test_validate_accepts_well_formed_manifest() -> None:
    assert m.validate_manifest(_manifest().to_dict()) == []


def test_counts_from_entries() -> None:
    manifest = _manifest()
    assert manifest.counts == m.Counts(total=3, ok=1, timed_out=1, error=0, skipped=1, skipped_by_reason={m.SKIP_THUNK: 1})
    assert [e.addr for e in manifest.ok_entries()] == [m.addr16(0x401000)]


@pytest.mark.parametrize(
    ["mutate", "fragment"],
    [
        (lambda d: d.pop("functions"), "functions: missing"),
        (lambda d: d.__setitem__("schema", "other/v1"), "schema: expected"),
        (lambda d: d.__setitem__("export_requires_java_decompile", False), "export_requires_java_decompile"),
        (lambda d: d["options"].__setitem__("sha256", "zz"), "options.sha256"),
        (lambda d: d["options"].__setitem__("simplification_style", "normalize"), "simplification_style"),
        (lambda d: d["capabilities"].__setitem__("supports", []), "capabilities.supports"),
        (lambda d: d["engine"].__setitem__("sla_format_version", "4"), "engine.sla_format_version"),
        (lambda d: d["engine"]["java_sla_sha256"].__setitem__("x86:LE:64:default", "short"), "engine.java_sla_sha256"),
        (lambda d: d["counts"].__setitem__("ok", 99), "counts.ok"),
        (lambda d: d["functions"][0].__setitem__("status", "weird"), "unknown status"),
        (lambda d: d["functions"][0].__setitem__("savefile", "functions/x.partial.xml"), "functions[0].savefile"),
        (lambda d: d["functions"][0].__setitem__("sha256", None), "functions[0].sha256"),
        (lambda d: d["functions"][0].__setitem__("oracle_c", None), "functions[0].oracle_c"),
        (lambda d: d["functions"][0].__setitem__("addr", "401000"), "functions[0].addr"),
        (lambda d: d["functions"][1].__setitem__("savefile", "functions/0000000000401040.xml"), "functions[1].savefile"),
        (lambda d: d["functions"][2].__setitem__("skip_reason", "because"), "functions[2].skip_reason"),
        (lambda d: d["functions"].append(dict(d["functions"][0])), "duplicate"),
        (lambda d: d["revision"].__setitem__("stale", "no"), "revision.stale: expected boolean"),
    ],
)
def test_validate_reports_problems(mutate, fragment: str) -> None:
    data = _manifest().to_dict()
    mutate(data)
    errors = m.validate_manifest(data)
    assert errors, "expected validation errors"
    assert any(fragment in err for err in errors), errors


def test_validate_rejects_non_object() -> None:
    assert m.validate_manifest([]) == ["manifest: expected a JSON object"]  # type: ignore[arg-type]


def test_stale_flag_round_trip_and_consistency() -> None:
    stale = _manifest(stale=True)
    assert stale.revision.stale is True
    assert m.validate_manifest(stale.to_dict()) == []
    data = stale.to_dict()
    data["revision"]["stale"] = False
    assert any("inconsistent with modification numbers" in err for err in m.validate_manifest(data))
    fresh = _manifest(stale=False)
    data = fresh.to_dict()
    data["revision"]["modification_number_after"] = 99
    assert any("inconsistent" in err for err in m.validate_manifest(data))


def test_overlay_entry_naming_validates() -> None:
    savefile = m.savefile_name("ovl0", 0x2000, True)
    stem = m.savefile_stem(savefile)
    entry = _entry(0x2000, space="ovl0", overlay=True, savefile=f"functions/{savefile}", oracle_c=f"oracle/{stem}.c", oracle_json=f"oracle/{stem}.json")
    manifest = _manifest([entry])
    assert manifest.functions[0].savefile == "functions/ovl0__0000000000002000.xml"
    assert m.validate_manifest(manifest.to_dict()) == []


def test_write_is_atomic_and_load_validates(tmp_path: Path) -> None:
    manifest = _manifest()
    target = tmp_path / "snap" / m.MANIFEST_FILENAME
    manifest.write(target)
    assert target.is_file()
    assert not target.with_name(target.name + ".tmp").exists()
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    loaded = m.load_manifest(tmp_path / "snap")
    assert loaded == manifest
    broken = json.loads(text)
    broken["schema"] = "nope"
    target.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid snapshot manifest"):
        m.Manifest.load(target)


def test_package_import_is_jvm_free() -> None:
    import importlib

    before = set(sys.modules)
    importlib.import_module("agentdecompile_recovery.native_snapshot")
    importlib.import_module("agentdecompile_recovery.native_snapshot.manifest")
    added = set(sys.modules) - before
    assert not any(name == "pyghidra" or name.startswith("pyghidra.") for name in added)
    assert not any(name == "jpype" or name.startswith("jpype.") for name in added)


class _TransactionInfo:
    def __init__(self, open_transactions: list[str]) -> None:
        self.open_transactions = open_transactions

    def getOpenSubTransactions(self) -> list[str]:
        return self.open_transactions


class _TransactionProgram:
    def __init__(self, info: object | None) -> None:
        self.info = info

    def getCurrentTransactionInfo(self) -> object | None:
        return self.info

def test_open_transaction_distinguishes_pyghidra_stale_info_from_live_work() -> None:
    assert not _has_open_transaction(_TransactionProgram(None))
    assert not _has_open_transaction(_TransactionProgram(_TransactionInfo([""])))
    assert not _has_open_transaction(_TransactionProgram(_TransactionInfo(["Batch Processing"])))
    assert _has_open_transaction(_TransactionProgram(_TransactionInfo([])))
    assert _has_open_transaction(_TransactionProgram(_TransactionInfo(["native-snapshot-test"])))
    assert _has_open_transaction(_TransactionProgram(_TransactionInfo(["Batch Processing", "native-snapshot-test"])))
