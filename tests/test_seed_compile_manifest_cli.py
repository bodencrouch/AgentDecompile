from pathlib import Path
from agentdecompile_recovery.corpus import cli, seed_validation
from agentdecompile_recovery.corpus.dashboard.actions.introspect import corpus_specs


def test_compile_manifest_reaches_public_handler_and_catalog(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(seed_validation,'audit',lambda **kw:calls.append(kw))
    manifest=tmp_path/'closure.json'
    args=['seed-validation','--seeds-dir',str(tmp_path/'seeds'),'--candidates',str(tmp_path/'candidates'),
          '--reuse',str(tmp_path/'reuse'),'--results',str(tmp_path/'results'),'--summary',str(tmp_path/'summary'),
          '--compile-input-manifest',str(manifest)]
    assert cli.main(args)==0
    assert calls[0]['compile_input_manifest']==manifest
    action={a.id:a for a in corpus_specs()}['corpus.seed-validation']
    assert 'compile-input-manifest' in {field.name for field in action.fields}
