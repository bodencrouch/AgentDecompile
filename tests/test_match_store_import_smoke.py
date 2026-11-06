"""Clean-tree import smoke for the store-backed matcher cascade."""

import importlib


def test_match_store_imports_cascade_deps():
    """Fail if cascade helpers are missing from the package (review #2)."""
    for mod in (
        "agentdecompile_recovery.corpus.callgraph_propagate",
        "agentdecompile_recovery.corpus.match_islands",
        "agentdecompile_recovery.corpus.block_inline",
        "agentdecompile_recovery.corpus.cfg_signature",
        "agentdecompile_recovery.corpus.mnemonic_spp",
        "agentdecompile_recovery.corpus.match_store",
    ):
        importlib.import_module(mod)
