"""Publication-journal binding scope: a legitimate binding never strands the
index, and a retained binding outside the journal's scope is refused before
any replay. Fixture-owned files only; no compiler or live corpus."""
import os

import pytest

from agentdecompile_recovery.corpus import cross_place_admission as gate
from agentdecompile_recovery.corpus import cross_place_checkpoint as cp


@pytest.fixture
def layout(tmp_path):
    out = tmp_path / 'out'
    donor = out / 'donor'
    donor.mkdir(parents=True)
    source = donor / 'leaf.c'
    source.write_bytes(b'source')
    receipt = out / 'receipt.json'
    receipt.write_bytes(b'{}')
    return out, source, receipt


def assert_index_usable(out, sequence):
    with cp.PublicationIndex(out).locked() as reopened:
        state = reopened.state()
        assert state['pending'] is None
        assert state.get('appendPending') is None
        assert state['sequence'] == sequence
        return reopened


def test_dotdot_binding_publish_does_not_strand_index(layout):
    out, source, receipt = layout
    # Only the binding carries '..'; files are canonical, as in
    # ghidra_bulk.distribute_compiled_source when source_bytes is None.
    dotted = out / 'donor' / '..' / 'donor' / 'leaf.c'
    index = cp.PublicationIndex(out)
    with index.locked():
        index.publish([(receipt, b'{"results":[]}')], [(dotted, receipt)])
    reopened = assert_index_usable(out, 1)
    event = cp.read(reopened.event_path(1))
    assert event['binding']['source']['path'] == str(source)
    assert event['binding']['receipt']['path'] == str(receipt)
    # Re-publishing the same binding through either spelling is idempotent.
    with reopened.locked():
        reopened.append(source, receipt)
        reopened.append(dotted, receipt)
    assert_index_usable(out, 1)


def test_dotdot_append_with_unavailable_receipt_does_not_strand_index(layout):
    out, source, _ = layout
    dotted_source = out / 'donor' / '..' / 'donor' / 'leaf.c'
    missing = out / 'donor' / '..' / 'missing.json'
    index = cp.PublicationIndex(out)
    with index.locked():
        index.append(dotted_source, missing)
    reopened = assert_index_usable(out, 1)
    event = cp.read(reopened.event_path(1))
    assert event['binding']['receipt'] == {'path': str(out / 'missing.json'), 'unavailable': True}


def _outside(tmp_path):
    outside = tmp_path / 'outside.json'
    outside.write_bytes(b'outside')
    return outside


@pytest.mark.parametrize('escape', ['receipt_outside', 'receipt_in_journal', 'source_in_journal', 'malformed'])
def test_recover_refuses_out_of_scope_binding_before_replay(tmp_path, layout, escape):
    out, source, receipt = layout
    outside = _outside(tmp_path)
    index = cp.PublicationIndex(out)
    with index.locked():
        pass
    stage = cp.directory(index.root / 'publication-fixture')
    staged = stage / '0'
    staged.write_bytes(b'new receipt')
    entry = {'path': str(receipt), 'before': gate.snapshot(receipt),
             'after': {'path': str(receipt), 'sha256': cp.hashlib.sha256(b'new receipt').hexdigest(), 'size': 11},
             'staged': str(staged)}
    journal_file = index.root / 'index.json'
    binding = {
        'receipt_outside': [str(source), str(outside)],
        'receipt_in_journal': [str(source), str(journal_file)],
        'source_in_journal': [str(journal_file), str(receipt)],
        'malformed': [str(source)],
    }[escape]
    row = index.state()
    row['pending'] = {'files': [entry], 'bindings': [binding]}
    cp.save(index.meta, row)
    retained = index.meta.read_bytes()
    with pytest.raises(ValueError, match='publication_binding'):
        with cp.PublicationIndex(out).locked():
            pass
    assert receipt.read_bytes() == b'{}'
    assert outside.read_bytes() == b'outside'
    assert index.meta.read_bytes() == retained
    assert not (index.root / 'events').exists() or not list((index.root / 'events').rglob('*.json'))


@pytest.mark.parametrize('escape', ['receipt_outside', 'receipt_in_journal', 'source_in_journal'])
def test_publish_refuses_out_of_scope_binding_before_intent(tmp_path, layout, escape):
    out, source, receipt = layout
    outside = _outside(tmp_path)
    index = cp.PublicationIndex(out)
    with index.locked():
        binding = {
            'receipt_outside': (source, outside),
            'receipt_in_journal': (source, index.meta),
            'source_in_journal': (index.meta, receipt),
        }[escape]
        with pytest.raises(ValueError, match='publication_binding'):
            index.publish([(receipt, b'new receipt')], [binding])
        assert index.state()['pending'] is None
    assert receipt.read_bytes() == b'{}'
    assert not list(index.root.glob('publication-*'))
    assert_index_usable(out, 0)


def test_hardlinked_binding_source_refused_before_intent(layout):
    out, source, receipt = layout
    os.link(source, out / 'alias.c')
    index = cp.PublicationIndex(out)
    with index.locked():
        with pytest.raises(ValueError, match='nonregular_or_hardlinked_input'):
            index.publish([(receipt, b'new receipt')], [(source, receipt)])
        assert index.state()['pending'] is None
    assert receipt.read_bytes() == b'{}'
    assert_index_usable(out, 0)
