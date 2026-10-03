from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus.dashboard.actions import catalog, introspect
from agentdecompile_recovery.corpus.pipeline import write_calibrate_global_receipt

pytestmark = pytest.mark.unit


def test_stub_profile_writes_partial_receipt(tmp_path: Path) -> None:
    profile = tmp_path / "compiler-profile.json"
    profile.write_text("{}", encoding="utf-8")
    receipt = write_calibrate_global_receipt(
        tmp_path,
        compiler_profile=profile,
    )
    assert receipt["wineStarted"] is False
    assert receipt["state"] == "partial"
    assert receipt["compiler"]["state"] == "present"
    assert receipt["types"] == "missing" or receipt["types"].get("state") == "missing"
    dest = tmp_path / "calibrate-global.json"
    assert dest.is_file()
    assert json.loads(dest.read_text(encoding="utf-8"))["state"] == "partial"


def test_missing_types_named_on_receipt(tmp_path: Path) -> None:
    receipt = write_calibrate_global_receipt(tmp_path)
    assert receipt["wineStarted"] is False
    assert receipt["state"] == "partial"
    assert "types" in receipt["gaps"]
    assert receipt["types"] == "missing" or receipt["types"].get("state") == "missing"


def test_catalog_lists_calibrate_global() -> None:
    ids = {item.id for item in catalog.list_actions()}
    assert "corpus.calibrate-global" in ids
    generated = {item.id for item in introspect.generate_actions()}
    assert "corpus.calibrate-global" in generated


def test_receipt_names_composed_fragments(tmp_path: Path) -> None:
    profile = tmp_path / "compiler-profile.json"
    profile.write_text("{}", encoding="utf-8")
    receipt = write_calibrate_global_receipt(tmp_path, compiler_profile=profile)
    fragments = receipt["fragments"]
    assert fragments["compiler-profile-corpus"]["state"] == "present"
    assert fragments["export-types"]["state"] == "missing"
    assert fragments["propagate"]["state"] == "missing"
    assert fragments["build-types-header"]["state"] == "missing"
    assert receipt["wineStarted"] is False


def test_calibrate_global_cli_requires_work_dir() -> None:
    from agentdecompile_recovery.corpus.cli import main as corpus_main

    with pytest.raises(SystemExit):
        corpus_main(["calibrate-global"])


@pytest.mark.parametrize('mode', ['absent', 'empty', 'populated', 'planned', 'error'])
def test_type_receipt_is_read_only_closes_handle_and_never_applies_or_starts(monkeypatch, tmp_path, mode):
    from agentdecompile_recovery.corpus import build_types_header as header
    from agentdecompile_recovery.corpus import export_types, propagate_types, store
    from tests.test_corpus_type_schema import current, snapshot, assert_read_only
    path = tmp_path / 'types.sqlite'
    writer = current(path, installed=mode not in ('absent',))
    if mode in ('populated', 'planned'):
        bids = (2,) if mode == 'planned' else (1, 2, 3)
        for bid in bids:
            writer.execute("INSERT INTO ghidra_type VALUES (?,'Layout','struct',4,'typedef int Layout;',0,NULL)", (bid,))
    writer.commit()
    durable = snapshot(writer)
    writer.execute("INSERT INTO eval(run) VALUES ('caller-pending')")
    pending = snapshot(writer)
    traces, handles = [], []
    original = store.connect
    class Reader:
        def __init__(self, con): self.con, self.closed = con, False
        def __getattr__(self, name): return getattr(self.con, name)
        def close(self):
            self.closed = True
            self.con.close()
    def opening(db, *, read_only=False, **kwargs):
        assert read_only is True
        con = original(db, read_only=read_only, **kwargs)
        con.set_trace_callback(traces.append)
        wrapper = Reader(con)
        handles.append(wrapper)
        return wrapper
    monkeypatch.setattr(store, 'connect', opening)
    def declared_basis(_con):
        if mode == 'error': raise ValueError('synthetic header basis failure')
        return {'toolchain_identity_hash': 'pinned:none'}
    monkeypatch.setattr(header, 'basis', declared_basis)
    monkeypatch.setattr(propagate_types.corpus_config, 'load_maps', lambda *_a, **_k: {})
    monkeypatch.setattr(export_types.ge, 'start', lambda: pytest.fail('planning started Ghidra'))
    monkeypatch.setattr(export_types, 'export', lambda *_a, **_k: pytest.fail('planning exported types'))
    monkeypatch.setattr(propagate_types, 'apply_adoptions', lambda *_a, **_k: pytest.fail('planning applied types'))
    receipt = write_calibrate_global_receipt(tmp_path / 'receipt', db=path)
    fragments = receipt['fragments']
    if mode == 'error':
        assert receipt['state'] == 'error' and receipt['errors']
    else:
        assert fragments['export-types']['state'] == ('missing' if mode == 'absent' else 'present')
        propagation = fragments['propagate']
        assert propagation['adopted'] == 0
        assert propagation['planned'] == (1 if mode == 'planned' else 0)
        assert propagation['state'] == ('planned' if mode == 'planned' else 'present')
        if mode == 'planned': assert 'propagation' in receipt['gaps']
        if mode == 'absent':
            assert fragments['build-types-header']['reason'] == 'no-type-inventory'
            assert not (tmp_path / 'receipt' / 'ghidra_types.h').exists()
        if mode == 'empty': assert fragments['build-types-header']['state'] == 'missing'
        if mode == 'populated': assert fragments['build-types-header']['state'] == 'present'
    assert receipt['wineStarted'] is False
    assert len(handles) == 1 and handles[0].closed
    assert_read_only(traces)
    assert snapshot(writer) == pending and writer.in_transaction
    writer.rollback()
    assert snapshot(writer) == durable
    writer.close()


def test_existing_header_bypasses_database_and_retains_fragment_contract(monkeypatch, tmp_path):
    from agentdecompile_recovery.corpus import store
    existing = tmp_path / 'types.h'
    existing.write_text('existing header\n')
    monkeypatch.setattr(store, 'connect', lambda *_a, **_k: pytest.fail('existing header should bypass database'))
    receipt = write_calibrate_global_receipt(tmp_path, db=tmp_path / 'unopened.sqlite', types_header=existing)
    assert receipt['fragments']['export-types'] == {'state': 'present', 'source': 'header-file'}
    assert receipt['fragments']['propagate'] == {'state': 'skipped', 'reason': 'header-file'}
    assert receipt['fragments']['build-types-header']['state'] == 'present'
    assert existing.read_text() == 'existing header\n'
