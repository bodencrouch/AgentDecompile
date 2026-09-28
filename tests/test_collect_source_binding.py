"""A historical success may not certify a different same-name source body."""
import json
from pathlib import Path

from agentdecompile_recovery.corpus.collect_source import collect
from agentdecompile_recovery.corpus.coverage_evidence import bind_source


def fixture_tree(tmp_path, code, row):
    projects = tmp_path / 'projects'
    project = projects / 'sample'
    project.mkdir(parents=True)
    (project / 'manifest.json').write_text(json.dumps({'program': 'sample.exe'}))
    result = {'results': [{'success': True, 'functionName': 'demo', 'attempts': [
        {'pluginResults': [{'pluginId': 'claude-runner', 'data': {'generatedCode': code}}]}]}]}
    (project / 'run-results-1.json').write_text(json.dumps(result))
    coverage = tmp_path / 'coverage'
    coverage.mkdir()
    (coverage / 'sample.exe.jsonl').write_text(json.dumps(row) + '\n')
    return {'projects_dir': projects, 'coverage_dir': coverage, 'out_dir': tmp_path / 'output'}


def test_legacy_success_does_not_certify_new_source(tmp_path):
    args = fixture_tree(tmp_path, 'int demo() { return 2; }', {'function': 'demo', 'byteExact': True})
    report = collect(**args)
    assert report['byte_exact'] == 0 and report['unverified'] == 1
    candidate = (args['out_dir'] / 'sample.exe/unverified/demo.c').read_text()
    assert 'NOT byte-exact-verified' in candidate
    assert 'satisfied objdiff' not in candidate
    assert not (args['out_dir'] / 'sample.exe/demo.c').exists()


def test_changed_same_name_source_remains_candidate(tmp_path):
    row = bind_source({'function': 'demo', 'byteExact': True}, b'int demo() { return 1; }')
    args = fixture_tree(tmp_path, 'int demo() { return 2; }', row)
    report = collect(**args)
    assert report['byte_exact'] == 0
    assert (args['out_dir'] / 'sample.exe/unverified/demo.c').exists()


def test_bound_source_output_is_byte_identical_no_header_or_whitespace_rewrite(tmp_path):
    code = 'int demo() { return 1; }  \r\n\r\n'
    row = bind_source({'function': 'demo', 'byteExact': True}, code.encode())
    args = fixture_tree(tmp_path, code, row)
    report = collect(**args)
    assert report['byte_exact'] == 1 and report['unverified'] == 0
    assert (args['out_dir'] / 'sample.exe/demo.c').read_bytes() == code.encode()


def test_false_verdict_with_matching_digest_stays_candidate(tmp_path):
    code = 'int demo() { return 1; }'
    row = bind_source({'function': 'demo', 'byteExact': False}, code.encode())
    args = fixture_tree(tmp_path, code, row)
    assert collect(**args)['byte_exact'] == 0


def test_later_bound_candidate_replaces_unbound_same_name(tmp_path, monkeypatch):
    from agentdecompile_recovery.corpus import collect_source
    correct = 'int demo() { return 1; }'
    row = bind_source({'function': 'demo', 'byteExact': True}, correct.encode())
    args = fixture_tree(tmp_path, 'int demo() { return 2; }', row)
    first = args['projects_dir'] / 'sample/run-results-1.json'
    second = first.with_name('run-results-2.json')
    data = json.loads(first.read_text())
    data['results'][0]['attempts'][0]['pluginResults'][0]['data']['generatedCode'] = correct
    second.write_text(json.dumps(data))
    monkeypatch.setattr(collect_source, 'iter_results', lambda _: iter([first, second]))
    assert collect(**args)['byte_exact'] == 1
    assert (args['out_dir'] / 'sample.exe/demo.c').read_bytes() == correct.encode()


def test_later_negative_withdraws_positive_and_quarantines_old_file(tmp_path):
    code = 'int demo() { return 1; }'
    row = bind_source({'function': 'demo', 'byteExact': True}, code.encode())
    args = fixture_tree(tmp_path, code, row)
    assert collect(**args)['byte_exact'] == 1
    old = args['out_dir'] / 'sample.exe/demo.c'
    with (args['coverage_dir'] / 'sample.exe.jsonl').open('a') as stream:
        stream.write(json.dumps({'function': 'demo', 'byteExact': False}) + '\n')
    report = collect(**args)
    assert report['byte_exact'] == 0 and not old.exists()
    assert len(report['quarantined']) == 1
    assert Path(report['quarantined'][0]['to']).read_bytes() == code.encode()
    assert (args['out_dir'] / 'sample.exe/unverified/demo.c').exists()


def test_sweep_with_no_current_results_withdraws_stale_verified_file(tmp_path):
    code = 'int demo() { return 1; }'
    row = bind_source({'function': 'demo', 'byteExact': True}, code.encode())
    args = fixture_tree(tmp_path, code, row)
    collect(**args)
    (args['projects_dir'] / 'sample/run-results-1.json').unlink()
    (args['coverage_dir'] / 'sample.exe.jsonl').write_text(json.dumps({'function':'demo','byteExact':False})+'\n')
    report = collect(**args)
    assert report['byte_exact'] == 0
    assert len(report['quarantined']) == 1
    assert not (args['out_dir'] / 'sample.exe/demo.c').exists()
    assert Path(report['quarantined'][0]['to']).read_bytes() == code.encode()


def test_retained_bound_file_counted_despite_new_unbound_candidate(tmp_path):
    code = 'int demo() { return 1; }'
    row = bind_source({'function': 'demo', 'byteExact': True}, code.encode())
    args = fixture_tree(tmp_path, code, row)
    collect(**args)
    result = args['projects_dir'] / 'sample/run-results-1.json'
    result.write_text(result.read_text().replace('return 1', 'return 2'))
    report = collect(**args)
    assert report['byte_exact'] == report['retained_verified'] == 1
    assert report['written_verified'] == 0 and report['unverified'] == 1
    assert report['programs']['sample.exe'] == [1, 1]
    assert (args['out_dir'] / 'sample.exe/demo.c').read_bytes() == code.encode()


def test_nonobject_ledger_records_ignored(tmp_path):
    args = fixture_tree(tmp_path, 'int demo() { return 1; }', {})
    ledger = args['coverage_dir'] / 'sample.exe.jsonl'
    ledger.write_text('null\n[]\ntrue\n42\n"text"\n')
    assert collect(**args)['unverified'] == 1
