"""Pure retry admission for one preparation action and its unchanged input basis.

Observation (job ownership, recovered prerequisites and failure classification) is
supplied by the coordinator. This module performs no IO and never resets spending.
"""
from __future__ import annotations

from typing import Any, Mapping

MAX_ACTION_ATTEMPTS = 3


def decide_retry(
    prior: Mapping[str, Any], *, transient: bool = False,
    prerequisite_recovered: bool = False, owner_available: bool = False,
    max_attempts: int = MAX_ACTION_ATTEMPTS, external_action: bool = False,
    external_restored: bool = False,
) -> dict[str, Any]:
    """Return eligibility, remaining spending and an exact non-dispatch reason."""
    raw_attempts = prior.get('attempts', 0)
    valid_count = isinstance(raw_attempts, int) and not isinstance(raw_attempts, bool) and raw_attempts >= 0
    attempts = raw_attempts if valid_count else max_attempts
    decision = {
        'schema': 'agentdecompile.preparation-retry.v1',
        'attemptsSpent': attempts, 'attemptsRemaining': max(0, max_attempts - attempts),
        'maxAttempts': max_attempts,
    }
    status = prior.get('status')
    result = prior.get('result') if isinstance(prior.get('result'), dict) else {}
    if not valid_count:
        kind, reason, wake = 'unknown_outcome', 'Stored attempt accounting is invalid; reconcile the action before dispatch.', 'reconciled_attempt_accounting'
    elif result.get('ownershipUnresolved') or result.get('unknownOutcome'):
        kind, reason, wake = 'unknown_outcome', 'Accepted work has an unknown outcome or unresolved ownership; reconcile before dispatch.', 'reconciled_terminal_receipt_and_resource_release'
    elif status == 'ok':
        kind, reason, wake = 'reuse_result', 'Reuse the recorded execution result; scientific acceptance remains a separate check.', ''
    elif status in {'submitting', 'queued', 'running', 'interrupted', 'cancelling'}:
        # Idempotence is not ownership: a disconnected worker may still hold
        # mutable resources. Do not create another worker merely to find out.
        kind = 'await_existing' if owner_available else 'unknown_outcome'
        reason = ('An accepted job still owns this action; wait for its terminal receipt.' if owner_available
                  else 'Completion of the accepted job is unknown; reconcile its output and ownership before resubmission.')
        wake = 'reconciled_terminal_receipt_and_resource_release'
    elif status == 'failed' and external_action and not external_restored:
        # Denied before starting (entitlement, billing, quota, disabled runner): not a failure
        # of the work itself, so it neither spends evidence nor retries until restored (FP-27).
        kind, reason, wake = ('external_action_required',
                              'An external entitlement or account action is required before this action can start.',
                              'external_entitlement_restored')
    elif attempts >= max_attempts:
        kind, reason, wake = 'budget_exhausted', f'Action retry budget exhausted ({attempts}/{max_attempts}) for these inputs; resume does not reset spending.', 'changed_relevant_input_basis'
    elif status == 'failed' and not (transient or prerequisite_recovered or (external_action and external_restored)):
        kind, reason, wake = 'wait_evidence', 'The recorded failure has no evidence that an unchanged retry can help.', 'changed_relevant_input_basis_or_verified_prerequisite'
    else:
        kind, reason, wake = 'dispatch', 'An attempt is available under the recorded input basis.', ''
    return {**decision, 'nextAction': kind, 'reason': reason, 'wakeCondition': wake}


def refusal_outcome(prior: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the decision without replacing the retained scientific result."""
    previous = prior.get('result') if isinstance(prior.get('result'), dict) else {}
    return {
        **previous, 'ok': False, 'error': str(decision['reason']), 'retryDecision': dict(decision),
        'nextAction': decision['nextAction'], 'wakeCondition': decision['wakeCondition'],
        'jobId': prior.get('jobId'), 'previousError': previous.get('error', ''),
    }
