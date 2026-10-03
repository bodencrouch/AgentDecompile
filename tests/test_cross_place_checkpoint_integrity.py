"""Checkpoint corruption and durability retry boundaries; synthetic files only."""
import json
import os
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import cross_place_checkpoint as checkpoint


def test_failed_parent_sync_is_retried_for_existing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint, "_DURABLE_DIRECTORIES", {})
    shard = tmp_path / "new-shard"
    fsync = os.fsync
    parent_barriers = []

    def fail_once(fd):
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if shard.exists() and target == tmp_path:
            parent_barriers.append(target)
            if len(parent_barriers) == 1:
                raise OSError("injected parent directory sync failure")
        return fsync(fd)

    monkeypatch.setattr(checkpoint.os, "fsync", fail_once)
    with pytest.raises(OSError, match="parent directory sync failure"):
        checkpoint.directory(shard)
    assert shard.is_dir()
    assert str(shard) not in checkpoint._DURABLE_DIRECTORIES
    checkpoint.directory(shard)
    assert len(parent_barriers) == 2
    assert checkpoint._DURABLE_DIRECTORIES[str(shard)] == (shard.stat().st_dev, shard.stat().st_ino)


@pytest.mark.parametrize("field,value", [
    ("state", "unknown"),
    ("state", None),
    ("count", 0),
    ("count", True),
    ("count", 3),
    ("notBefore", float("nan")),
    ("notBefore", float("inf")),
    ("notBefore", "0"),
    ("notBefore", None),
    ("reservedAt", -1),
    ("monotonic", False),
])
def test_corrupt_reservation_refuses_without_resetting_record(tmp_path, field, value):
    ledger = checkpoint.Ledger(tmp_path / "area")
    key = "c" * 64
    assert ledger.reserve(key)[0]
    path = ledger.path(key)
    row = json.loads(path.read_bytes())
    row[field] = value
    # Deliberately bypass the writer to model damaged persisted input.
    path.write_text(json.dumps(row, allow_nan=True))
    corrupted = path.read_bytes()
    with pytest.raises(ValueError, match="checkpoint_"):
        checkpoint.Ledger(ledger.area).reserve(key)
    assert path.read_bytes() == corrupted


def test_malformed_publication_cannot_become_a_fresh_attempt(tmp_path):
    ledger = checkpoint.Ledger(tmp_path / "area")
    key = "d" * 64
    assert ledger.reserve(key)[0]
    path = ledger.path(key)
    row = json.loads(path.read_bytes())
    row.update(state="publishing", count=0, publication={"path": "missing"})
    path.write_text(json.dumps(row))
    corrupted = path.read_bytes()
    with pytest.raises(ValueError, match="checkpoint_"):
        checkpoint.Ledger(ledger.area).reused(key)
    assert path.read_bytes() == corrupted
