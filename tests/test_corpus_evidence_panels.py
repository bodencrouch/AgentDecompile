"""Corpus evidence panels: payload contract, endpoint cache, config-driven targets."""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus import corpus_config, db
from agentdecompile_recovery.corpus.dashboard import common, pages

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "src" / "agentdecompile_recovery" / "corpus" / "dashboard" / "static"
EVIDENCE_PANELS = ("binaries", "crossmatch", "directives", "knowledge",
                   "processes", "recovery", "roundtrip", "stabs")
MARKUP = re.compile(r"<(div|span|a|p|table|svg|li|ul|pre|code|details)[\s>]", re.I)
CORPUS_ENV = ("AGENT_DECOMPILE_CORPUS_ROOT", "AGENT_DECOMPILE_CORPUS_WORK_DIR",
              "AGENT_DECOMPILE_CORPUS_DB", "AGENT_DECOMPILE_KNOWLEDGE_DB",
              "AGENT_DECOMPILE_GHIDRA_KNOWLEDGE_DB", "AGENT_DECOMPILE_EXTERNAL_RECOVERY_ROOT",
              "AGENT_DECOMPILE_GHIDRA_SERVER_HOST", "AGENT_DECOMPILE_GHIDRA_SERVER_PORT",
              "AGENT_DECOMPILE_EXCLUDED_REPO_PATHS")


def _panel(name: str):
    return importlib.import_module(f"agentdecompile_recovery.corpus.dashboard.panels.{name}")


@pytest.fixture
def empty_corpus(tmp_path, monkeypatch):
    """A corpus root with no artifacts and an empty database."""
    for name in CORPUS_ENV:
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "corpus"
    root.mkdir()
    corpus_db = tmp_path / "corpus.db"
    db.connect(corpus_db).close()
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_ROOT", str(root))
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_WORK_DIR", str(root))
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_DB", str(corpus_db))
    monkeypatch.setenv("AGENT_DECOMPILE_EXTERNAL_RECOVERY_ROOT", str(tmp_path / "external"))
    importlib.reload(common)
    for name in EVIDENCE_PANELS:
        importlib.reload(_panel(name))
    yield root
    monkeypatch.undo()
    importlib.reload(common)
    for name in EVIDENCE_PANELS:
        importlib.reload(_panel(name))


@pytest.mark.parametrize("name", EVIDENCE_PANELS)
def test_panel_payload_is_structured_data(empty_corpus, name):
    payload = _panel(name).as_payload()
    text = json.dumps(payload, default=str)
    assert isinstance(payload, dict)
    assert isinstance(payload.get("errors"), list)
    assert not MARKUP.search(text), f"{name} payload carries markup"


@pytest.mark.parametrize("name", EVIDENCE_PANELS)
def test_panel_render_and_payload_share_one_collector(empty_corpus, name):
    module = _panel(name)
    assert isinstance(module.render(), str)
    assert callable(module.as_payload)


def test_recovery_keeps_real_c_byte_exact_and_asm_floor_separate(empty_corpus):
    payload = _panel("recovery").as_payload()
    assert {"real_c", "byte_exact", "asm_floor"} <= set(payload)
    for key in ("real_c_and_byte_exact", "sampled", "compiles_unmodified", "real_c_source_bodies"):
        assert {"value", "source", "state"} <= set(payload["byte_exact"][key])


def test_crossmatch_keeps_identity_and_propagation_apart(empty_corpus):
    payload = _panel("crossmatch").as_payload()
    assert "identity" in payload and "propagation" in payload
    assert "never summed" in payload["notes"]["identity_vs_propagation"]


def test_panel_endpoint_caches_collection_per_ttl(monkeypatch):
    calls = []

    def collect():
        calls.append(1)
        return {"errors": [], "value": len(calls)}

    section = pages.SECTION_BY_ID["directives"]
    monkeypatch.setattr(section, "module", SimpleNamespace(as_payload=collect))
    pages._CACHE.pop("payload:directives", None)
    try:
        first, status = pages.panel_payload_json("directives")
        second, _ = pages.panel_payload_json("directives")
    finally:
        pages._CACHE.pop("payload:directives", None)
    assert status == 200
    assert len(calls) == 1
    assert first["payload"] == second["payload"] == {"errors": [], "value": 1}
    assert first["collectedAt"] is not None
    assert first["window"] == "wb-mission"


def test_panel_endpoint_reports_a_raising_collector(monkeypatch):
    def collect():
        raise RuntimeError("store unreadable")

    section = pages.SECTION_BY_ID["knowledge"]
    monkeypatch.setattr(section, "module", SimpleNamespace(as_payload=collect))
    pages._CACHE.pop("payload:knowledge", None)
    try:
        body, status = pages.panel_payload_json("knowledge")
    finally:
        pages._CACHE.pop("payload:knowledge", None)
    assert status == 200
    assert "store unreadable" in body["payload"]["error"]
    assert any("store unreadable" in e for e in body["payload"]["errors"])


def test_unknown_panel_is_404():
    body, status = pages.panel_payload_json("no-such-panel")
    assert status == 404 and body["ok"] is False


@pytest.fixture
def program_configs(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    (cfg / "programs").mkdir(parents=True)
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("CORPUS_PROGRAM", raising=False)
    monkeypatch.delenv("CORPUS_CONFIG", raising=False)

    def write(name: str, data: dict) -> None:
        (cfg / "programs" / f"{name}.json").write_text(json.dumps(data))

    return write


def test_program_section_finds_the_single_carrier(program_configs):
    program_configs("alpha.exe", {"repo_path": "/A/alpha.exe", "permuter": {"compiler": "c1"}})
    program_configs("beta.exe", {"repo_path": "/B/beta.exe"})
    name, raw = corpus_config.program_section("permuter")
    assert name == "alpha.exe"
    assert raw["permuter"]["compiler"] == "c1"


def test_program_section_refuses_ambiguity_and_absence(program_configs, monkeypatch):
    program_configs("alpha.exe", {"permuter": {}})
    program_configs("beta.exe", {"permuter": {}})
    with pytest.raises(LookupError, match="2 program configs"):
        corpus_config.program_section("permuter")
    with pytest.raises(LookupError, match="no 'parity' section"):
        corpus_config.program_section("parity", "alpha.exe")
    monkeypatch.setenv("CORPUS_PROGRAM", "beta.exe")
    assert corpus_config.program_section("permuter")[0] == "beta.exe"


def test_permuter_target_comes_from_program_config(program_configs, tmp_path):
    from agentdecompile_recovery.corpus import text_permuter_watch as tpw

    corpus = tmp_path / "corpus.sqlite"
    con = db.connect(corpus)
    con.execute("INSERT INTO binary (repo_path, slug) VALUES ('/G/app.exe', 'G__app.exe')")
    con.commit()
    paths = {k: str(tmp_path / k) for k in
             ("toolkit_root", "candidate_dir", "queue_diffs", "state", "status", "byteexact_dir", "work_dir")}
    program_configs("app.exe", {"repo_path": "/G/app.exe",
                                "permuter": {**paths, "database": str(corpus), "compiler": "c1"}})
    target = tpw.load_target()
    assert target.program == "app.exe" and target.compiler == "c1"
    assert target.database == corpus
    assert tpw._binary_id(con, target.repo_path) == 1
    with pytest.raises(LookupError):
        tpw._binary_id(con, "/G/other.exe")
    con.close()


def test_permuter_names_missing_config_keys(program_configs):
    from agentdecompile_recovery.corpus import text_permuter_watch as tpw

    program_configs("app.exe", {"repo_path": "/G/app.exe", "permuter": {"compiler": "c1"}})
    with pytest.raises(LookupError, match="toolkit_root"):
        tpw.load_target()
    assert tpw.main(["--limit", "1"]) == 2


def test_byte_parity_reads_paths_from_program_config(program_configs, tmp_path):
    from agentdecompile_recovery.corpus.dashboard import byte_parity

    target = tmp_path / "target.bin"
    target.write_bytes(b"same")
    rebuilt = tmp_path / "rebuilt.bin"
    shutil.copy(target, rebuilt)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"closed": {"0x1": {}, "0x2": {}}}))
    program_configs("app.exe", {
        "permuter": {"state": str(state)},
        "parity": {"target_image": str(target), "rebuilt_image": str(rebuilt)},
    })
    result = byte_parity.byte_parity_state()
    assert result["targetHash"] == result["rebuiltHash"] is not None
    assert result["textPermuterClosed"] == 2


def test_byte_parity_without_config_degrades(monkeypatch, tmp_path):
    from agentdecompile_recovery.corpus.dashboard import byte_parity

    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_CONFIG_DIR", str(tmp_path / "none"))
    monkeypatch.delenv("CORPUS_PROGRAM", raising=False)
    assert byte_parity._parity_config() == {}
    result = byte_parity.byte_parity_state()
    assert result["targetHash"] is None and result["textPermuterClosed"] == 0


def test_db_connect_defaults_to_the_configured_corpus(monkeypatch, tmp_path):
    target = tmp_path / "configured.db"
    monkeypatch.setenv("AGENT_DECOMPILE_CORPUS_DB", str(target))
    assert db.default_path() == target
    db.connect().close()
    assert target.exists()


def test_workbench_mounts_every_evidence_panel_in_its_window():
    app = (STATIC / "workbench-app.js").read_text(encoding="utf-8")
    css = (STATIC / "workbench-editor.css").read_text(encoding="utf-8")
    assert "function PanelEvidence(" in app
    for panel_id, window in pages.PANEL_WINDOW.items():
        if panel_id not in EVIDENCE_PANELS:
            continue
        block = app.split(f'if (tab === "{window}")', 1)[1].split("if (tab ===", 1)[0]
        assert f'evidence("{panel_id}"' in block, f"{panel_id} is not mounted in {window}"
    assert ".wb-ev-panel" in css
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", css.split("Corpus evidence", 1)[1])


def test_no_external_project_name_in_tracked_source():
    if not shutil.which("git"):
        pytest.skip("git unavailable")
    proc = subprocess.run(["git", "-C", str(REPO), "grep", "-il", "kotorxid", "--", "src"],
                          capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1):
        pytest.skip("not a git checkout")
    assert proc.stdout.strip() == ""
