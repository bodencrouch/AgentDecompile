"""Inventory context and finite-epoch behavior without native compilation."""
from agentdecompile_recovery.corpus import cross_place_checkpoint as checkpoint


def test_same_source_keeps_each_selected_receipt_across_resume(tmp_path):
    output = tmp_path / "output"
    source_dir = output / "donor"
    source_dir.mkdir(parents=True)
    source = source_dir / "leaf.c"
    source.write_bytes(b"source")
    first = output / "a.json"
    second = output / "b.json"
    first.write_bytes(b"first receipt")
    second.write_bytes(b"second receipt")
    index = checkpoint.PublicationIndex(output)
    with index.locked():
        index.append(source, first)
        index.append(source, second)
    ledger = checkpoint.Ledger(output / ".cross-place")
    parameters = {"receipt": str(first)}
    scan = checkpoint.Scan(ledger, source_dir, parameters)
    assert scan.pending() == [(source, str(first)), (source, str(second))]
    scan.set_context(first)
    scan.progress(source)

    resumed = checkpoint.Scan(checkpoint.Ledger(output / ".cross-place"), source_dir, parameters)
    resumed.set_context(first)
    assert resumed.skip(source)
    resumed.set_context(second)
    assert not resumed.skip(source)
    assert (source, str(second)) in resumed.pending()
    resumed.progress(source, (2, 4096))

    again = checkpoint.Scan(ledger, source_dir, parameters)
    again.set_context(second)
    assert again.skip(source, (2, 4096))
    assert not again.skip(source, (3, 4096))


def test_new_earlier_source_waits_for_next_finite_epoch_then_is_discovered(tmp_path):
    output = tmp_path / "output"
    source_dir = output / "donor"
    source_dir.mkdir(parents=True)
    receipt = output / "receipt.json"
    receipt.write_bytes(b"receipt")
    original = source_dir / "middle.c"
    original.write_bytes(b"middle")
    index = checkpoint.PublicationIndex(output)
    with index.locked():
        index.append(original, receipt)
    ledger = checkpoint.Ledger(output / ".cross-place")
    parameters = {"receipt": str(receipt)}
    scan = checkpoint.Scan(ledger, source_dir, parameters)
    assert scan.pending() == [(original, str(receipt))]
    assert scan.row["highwater"] == 1

    earlier = source_dir / "a.c"
    earlier.write_bytes(b"earlier")
    with index.locked():
        index.append(earlier, receipt)
        for number in range(3):
            tail = source_dir / f"z{number}.c"
            tail.write_bytes(b"tail")
            index.append(tail, receipt)
    # Later arrivals cannot extend membership of the already sealed epoch.
    assert scan.pending() == [(original, str(receipt))]
    assert scan.row["highwater"] == 1
    scan.finish()

    resumed = checkpoint.Scan(ledger, source_dir, parameters)
    assert (earlier, str(receipt)) in resumed.pending()
    assert resumed.row["highwater"] == 5
    assert resumed.row["epoch"] == 2
