from __future__ import annotations

import pytest

from agentdecompile_recovery.corpus.dashboard.preparation import (
    _action_prior_for_retry,
    _matching_inventory_progress_kwargs,
)

pytestmark = pytest.mark.unit


def test_matching_inventory_progress_keeps_pair_total() -> None:
    progress = _matching_inventory_progress_kwargs(
        pair_count=459,
        inventory_completed=3,
        inventory_total=28,
        current_program='k1.exe',
        source='/repo/k2.exe',
        functions_read=12000,
    )
    assert progress['completed'] == 0
    assert progress['total'] == 459
    assert progress['progressUnit'] == 'comparisons'
    assert progress['currentProgram'] == 'k1.exe'
    assert progress['workProgress'] == {
        'completed': 3,
        'total': 28,
        'unit': 'binary inventories',
    }
    assert 'k2.exe' in progress['_reason_detail']
    assert '12,000' in progress['_reason_detail']


def test_match_pair_failed_prior_preserves_spent_attempts() -> None:
    prior = {
        'status': 'failed',
        'attempts': 3,
        'result': {'ok': False, 'error': 'ImportError: cannot import name mizuchi_tools_cli'},
    }
    assert _action_prior_for_retry('corpus.match-pair', prior) is prior


def test_non_match_pair_failed_prior_is_preserved() -> None:
    prior = {'status': 'failed', 'result': {'ok': False, 'error': 'permanent'}}
    assert _action_prior_for_retry('corpus.ghidra-bulk', prior) is prior


def test_matching_inventory_progress_without_source_detail() -> None:
    progress = _matching_inventory_progress_kwargs(
        pair_count=12,
        inventory_completed=0,
        inventory_total=4,
    )
    assert progress['total'] == 12
    assert progress['workProgress']['total'] == 4
    assert progress['_reason_detail'] == ''
