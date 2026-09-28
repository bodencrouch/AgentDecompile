"""Private publication-journal failure fixtures; no compiler or live corpus.

Injected exceptions exercise restart protocol boundaries, not power-loss survival.
"""
import hashlib
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import cross_place_checkpoint as journal


@pytest.fixture
def publication(tmp_path):
    output = tmp_path / "output"
    source_dir = output / "donor"
    source_dir.mkdir(parents=True)
    source = source_dir / "leaf.c"
    receipt = output / "receipt.json"
    source.write_bytes(b"old source")
    receipt.write_bytes(b"old receipt")
    return output, source_dir, source, receipt


@pytest.mark.parametrize("failed_target", ["source", "receipt"])
def test_interrupted_pair_replays_from_durable_intent(publication, monkeypatch, failed_target):
    output, _, source, receipt = publication
    index = journal.PublicationIndex(output)
    replace = journal.os.replace
    target = source if failed_target == "source" else receipt

    def interrupt(src, dst):
        if Path(dst) == target:
            raise OSError("injected publication rename interruption")
        return replace(src, dst)

    with index.locked():
        with monkeypatch.context() as patch:
            patch.setattr(journal.os, "replace", interrupt)
            with pytest.raises(OSError, match="rename interruption"):
                index.publish([(source, b"new source"), (receipt, b"new receipt")],
                              [(source, receipt)])
        assert index.state()["pending"] is not None
        assert index.state()["sequence"] == 0
    # A fresh object and lock acquisition must recover without directory search.
    restarted = journal.PublicationIndex(output)
    with restarted.locked():
        assert source.read_bytes() == b"new source"
        assert receipt.read_bytes() == b"new receipt"
        assert restarted.state()["pending"] is None
        assert restarted.state()["sequence"] == 1
        event = journal.read(restarted.event_path(1))
        assert event["binding"]["source"]["sha256"] == hashlib.sha256(b"new source").hexdigest()
        assert event["binding"]["receipt"]["sha256"] == hashlib.sha256(b"new receipt").hexdigest()
    with journal.PublicationIndex(output).locked() as reopened:
        assert reopened.state()["sequence"] == 1


def test_recovery_preserves_conflicting_external_source(publication, monkeypatch):
    output, _, source, receipt = publication
    index = journal.PublicationIndex(output)
    with index.locked():
        with monkeypatch.context() as patch:
            def interrupt():
                raise OSError("injected after intent")
            patch.setattr(index, "recover", interrupt)
            with pytest.raises(OSError, match="after intent"):
                index.publish([(source, b"new source"), (receipt, b"new receipt")],
                              [(source, receipt)])
    source.write_bytes(b"external writer owns these bytes")
    pending_before = index.meta.read_bytes()
    with pytest.raises(ValueError, match="external_conflict"):
        with journal.PublicationIndex(output).locked():
            pytest.fail("conflicting publication must not enter the consumer")
    assert source.read_bytes() == b"external writer owns these bytes"
    assert receipt.read_bytes() == b"old receipt"
    assert index.meta.read_bytes() == pending_before


def test_event_commit_interruption_does_not_lose_or_duplicate_binding(publication, monkeypatch):
    output, _, source, receipt = publication
    index = journal.PublicationIndex(output)
    save = journal.save
    with index.locked():
        with monkeypatch.context() as patch:
            def interrupt(path, value):
                if Path(path) == index.meta and value.get("sequence") == 1:
                    raise OSError("injected after event before sequence")
                return save(path, value)
            patch.setattr(journal, "save", interrupt)
            with pytest.raises(OSError, match="before sequence"):
                index.publish([(source, b"new source"), (receipt, b"new receipt")],
                              [(source, receipt)])
        assert index.event_path(1).is_file()
        assert index.state()["sequence"] == 0
    with journal.PublicationIndex(output).locked() as restarted:
        assert restarted.state()["sequence"] == 1
        assert restarted.state()["pending"] is None
        restarted.append(source, receipt)
        assert restarted.state()["sequence"] == 1


def test_manifest_import_resumes_after_first_chunk_without_reenrollment(publication):
    output, source_dir, source, receipt = publication
    # 129 entries cross the actual immutable inventory chunk size.
    for number in range(128):
        (source_dir / f"entry_{number:03d}.c").write_bytes(b"source")
    index = journal.PublicationIndex(output)
    with index.locked():
        state = index.bootstrap(source_dir, receipt)
        assert state["complete"] is True
        cursor, total = index.import_manifest(state["manifest"], state["sha256"])
        assert (cursor, total) == (1, 2)
        assert index.state()["sequence"] == 128
    with journal.PublicationIndex(output).locked() as restarted:
        cursor, total = restarted.import_manifest(state["manifest"], state["sha256"], cursor)
        assert (cursor, total) == (2, 2)
        assert restarted.state()["sequence"] == 129
        assert restarted.import_manifest(state["manifest"], state["sha256"], cursor) == (2, 2)
        enrolled = {journal.read(restarted.event_path(i))["binding"]["source"]["path"]
                    for i in range(1, 130)}
        assert enrolled == {str(path) for path in source_dir.glob("*.c")}
        assert str(source) in enrolled


def test_committed_sequence_recovers_latest_binding_without_duplicate(publication, monkeypatch):
    output, _, source, receipt = publication
    index = journal.PublicationIndex(output)
    save = journal.save
    with index.locked():
        with monkeypatch.context() as patch:
            def interrupt(path, value):
                if index.root / "latest" in Path(path).parents:
                    raise OSError("injected latest binding failure")
                return save(path, value)
            patch.setattr(journal, "save", interrupt)
            with pytest.raises(OSError, match="latest binding failure"):
                index.publish([(source, b"new source"), (receipt, b"new receipt")],
                              [(source, receipt)])
    with journal.PublicationIndex(output).locked() as restarted:
        assert restarted.state()["sequence"] == 1
        restarted.append(source, receipt)
        assert restarted.state()["sequence"] == 1
        assert restarted.state()["pending"] is None


def test_direct_enrollment_recovers_before_enrolling_different_source(publication, monkeypatch):
    output, source_dir, source, receipt = publication
    other = source_dir / "other.c"
    other.write_bytes(b"other source")
    index = journal.PublicationIndex(output)
    save = journal.save
    with index.locked():
        with monkeypatch.context() as patch:
            def interrupt(path, value):
                if Path(path) == index.meta and value.get("sequence") == 1:
                    raise OSError("injected enrollment sequence failure")
                return save(path, value)
            patch.setattr(journal, "save", interrupt)
            with pytest.raises(OSError, match="enrollment sequence failure"):
                index.append(source, receipt)
    with journal.PublicationIndex(output).locked() as restarted:
        restarted.append(other, receipt)
        assert restarted.state()["sequence"] == 2
        enrolled = [journal.read(restarted.event_path(i))["binding"]["source"]["path"]
                    for i in (1, 2)]
        assert enrolled == [str(source), str(other)]
        restarted.append(source, receipt)
        restarted.append(other, receipt)
        assert restarted.state()["sequence"] == 2


def test_changed_manifest_chunk_refuses_before_any_enrollment(publication):
    output, source_dir, _, receipt = publication
    index = journal.PublicationIndex(output)
    with index.locked():
        state = index.bootstrap(source_dir, receipt)
        inventory = journal.read(state["manifest"])
        chunk = Path(inventory["chunks"][0]["path"])
        chunk.write_bytes(b'{"names":["different.c"]}')
        with pytest.raises(ValueError, match="import_chunk_changed"):
            index.import_manifest(state["manifest"], state["sha256"])
        assert index.state()["sequence"] == 0


@pytest.mark.parametrize("damage", ["missing", "invalid_json", "wrong_sequence"])
def test_event_gap_refuses_without_advancing_durable_scan(publication, damage):
    output, source_dir, source, receipt = publication
    index = journal.PublicationIndex(output)
    with index.locked():
        index.append(source, receipt)
        event_path = index.event_path(1)
        if damage == "missing":
            event_path.unlink()
        elif damage == "invalid_json":
            event_path.write_bytes(b"{broken event")
        else:
            event = journal.read(event_path)
            event["sequence"] = 2
            journal.save(event_path, event)
    ledger = journal.Ledger(output / ".cross-place")
    scan = journal.Scan(ledger, source_dir, {"receipt": str(receipt)})
    before = scan.path.read_bytes()
    # No pending work may escape to qualification from an incomplete journal.
    with pytest.raises((OSError, ValueError)):
        scan.pending()
    assert scan.path.read_bytes() == before
    assert scan.row["frontier"] == 0
    assert scan.row["sealed"] is False
