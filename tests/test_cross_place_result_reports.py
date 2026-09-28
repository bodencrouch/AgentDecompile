"""Synthetic report transport proof; reporting never supplies admission authority."""
import json
from pathlib import Path
import pytest
from agentdecompile_recovery.corpus import cross_place as cp
from agentdecompile_recovery.corpus import cross_place_checkpoint as checkpoint


def test_capacity_report_and_successor_aggregate_all_129_rows(tmp_path):
    ledger = checkpoint.Ledger(tmp_path / '.cross-place')
    aggregate = checkpoint.ResultReport(ledger, 'aggregate', 'run')
    summaries = []
    for generation, count in [('capacity', 128), ('successor', 1)]:
        worker = checkpoint.ResultReport(ledger, 'worker', generation)
        for i in range(count):
            worker.add({'published': True, 'qualified': True, 'candidate': f'{generation}-{i}'}, 'placed')
        summary = worker.finish(); summaries.append(summary)
        checkpoint.consume_report(ledger, summary, generation, aggregate.add)
    result = aggregate.finish()
    assert [s['placed'] for s in summaries] == [128, 1]
    assert result['placed'] == result['resultCount'] == 129
    assert result['resultsTruncated'] is True and len(result['results']) == 128
    rows = [json.loads(line)['row'] for line in Path(result['completeResults']['path']).read_text().splitlines()[1:]]
    assert len(rows) == 129 and rows[-1]['candidate'] == 'successor-0'
    assert sorted(p.name for p in (ledger.root / 'reports').iterdir()) == ['aggregate-results.jsonl', 'worker-results.jsonl']


@pytest.mark.parametrize('change', ['bytes', 'scope', 'count', 'inline', 'truncation'])
def test_report_refuses_changed_artifact_or_generation(tmp_path, change):
    ledger = checkpoint.Ledger(tmp_path / '.cross-place')
    report = checkpoint.ResultReport(ledger, 'worker', 'one')
    report.add({'published': False, 'qualified': True}, 'idempotent')
    summary = report.finish()
    if change == 'bytes':
        p = Path(summary['completeResults']['path']); p.write_bytes(p.read_bytes().replace(b'true', b'null'))
    elif change == 'scope': summary['completeResults']['token'] = 'other'
    elif change == 'count': summary['idempotent'] = 9
    elif change == 'inline': summary['results'] = [{'forged': True}]
    else: summary['resultsTruncated'] = True
    received = []
    with pytest.raises(ValueError, match='report_'):
        checkpoint.consume_report(ledger, summary, 'one', lambda row, category: received.append((row, category)))
    assert received == []


def test_small_report_keeps_original_inline_results(tmp_path):
    ledger = checkpoint.Ledger(tmp_path / '.cross-place')
    report = checkpoint.ResultReport(ledger, 'worker', 'one')
    row = {'candidate': 'one', 'qualified': False, 'published': True}
    report.add(row, 'proposed'); report.add(None, 'skipped_no_addr')
    summary = report.finish()
    assert summary['results'] == [row] and summary['resultsTruncated'] is False
    assert checkpoint.consume_report(ledger, summary, 'one') == {
        'placed': 0, 'proposed': 1, 'idempotent': 0, 'skipped_no_addr': 1}


def test_explicit_source_root_never_substitutes_same_basename(tmp_path):
    actual = tmp_path / 'external/donor'; actual.mkdir(parents=True)
    wrong = tmp_path / 'output/donor'; wrong.mkdir(parents=True)
    (wrong / 'wrong.c').write_text('wrong')
    params = {'from': 'donor', 'source-dir': str(actual), 'out-dir': str(wrong.parent)}
    assert cp.selected_source(params) == actual
    actual.rmdir()
    with pytest.raises(ValueError, match='source_directory_unavailable'):
        cp.selected_source(params)


def test_main_aggregates_capacity_and_successor_into_single_json(tmp_path, monkeypatch, capsys):
    # Controlled report protocol transport, not native or clearance evidence.
    out=tmp_path/'out';src=out/'donor';src.mkdir(parents=True)
    source=src/'one.c';source.write_text('int one(void){return 7;}')
    (out/'compile-receipt.json').write_text('{}')
    db=tmp_path/'db.sqlite';db.write_bytes(b'fixture file only')
    raw=tmp_path/'raw';raw.mkdir()
    generations=[]
    def execute(argv,fds,event,on_started=None):
        payload=json.loads(argv[-1]);params=payload['params'];envelope=payload['generation']
        ledger=checkpoint.Ledger(out/'.cross-place')
        scan=checkpoint.Scan(ledger,src,{'repo':params['repo'],'db':params['db'],
            'raw':params['raw-dir'],'receipt':params['byteexact-receipt'],'exploration':False})
        report=checkpoint.ResultReport(ledger,'worker',envelope['generation'])
        count=128 if not generations else 1
        for i in range(count):report.add({'candidate':f'{len(generations)}-{i}','published':True,'qualified':True},'placed')
        code=75 if not generations else 0
        if code==75:
            scan.set_context(params['byteexact-receipt']);scan.progress(source,(128,4096))
        else:scan.finish()
        generations.append(code)
        return code,json.dumps({'event':'cross-place-generation','generation':envelope['generation'],
            'status':'capacity' if code==75 else 'complete','report':report.finish()})
    monkeypatch.setattr(cp,'_standalone_execute',execute)
    assert cp.main(['--from','donor','--db',str(db),'--repo','/donor.exe',
        '--out-dir',str(out),'--raw-dir',str(raw)])==0
    summary=json.loads(capsys.readouterr().out)
    assert generations==[75,0]
    assert summary['placed']==summary['resultCount']==129 and summary['resultsTruncated'] is True
    rows=Path(summary['completeResults']['path']).read_text().splitlines()
    assert len(rows)==130 and json.loads(rows[-1])['row']['candidate']=='1-0'
