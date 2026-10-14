"""Narrow, durable reservation reclassification for audited read-only providers."""

from __future__ import annotations

import json
import time
from typing import Any


def reclassify_read_only_provider(job_id: str) -> dict[str, Any]:
    """Move a timed-out get-references DB claim to its exact Ghidra project.

    The remote call may still be running after the HTTP timeout. This never
    clears ownership: it retains the same job as a quarantined Ghidra owner.
    """
    from agentdecompile_cli.registry import get_tool_metadata
    from agentdecompile_recovery.corpus.dashboard.actions import job_history, jobs
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import action_by_id
    from agentdecompile_recovery.corpus.dashboard.actions.jobs import ghidra_lock_key, identity_lock_key
    from agentdecompile_recovery.corpus.dashboard.common import live_db
    from agentdecompile_recovery.corpus.supervision import save_state

    store = jobs.STORE
    with store._lock:
        if (not isinstance(job_id, str) or len(job_id) not in (12, 16, 24, 32)
                or any(char not in '0123456789abcdef' for char in job_id)):
            raise ValueError('Invalid job identity.')
        root = job_history.directory()
        if root is None:
            raise OSError('Durable job receipt store is unavailable.')
        path = root / (job_id + '.json')
        if path.is_symlink():
            raise ValueError('Durable receipt is a symlink; reservation retained.')
        row = json.loads(path.read_text())
        current = store._jobs.get(job_id)
        if not isinstance(row, dict) or row.get('id') != job_id:
            raise ValueError('Durable receipt identity mismatch; reservation retained.')
        params, keys = row.get('params'), row.get('resourceKeys')
        if not isinstance(params, dict) or not isinstance(keys, dict):
            raise ValueError('Receipt lacks exact parameters or resource keys; reservation retained.')

        action = action_by_id('mcp.get-references')
        metadata = get_tool_metadata('get-references')
        db_access = getattr(metadata, 'corpus_db_access', None)
        ghidra_access = getattr(metadata, 'ghidra_session_access', None)
        if (action is None or action.command != 'get-references' or action.mutating
                or not action.ghidra_exclusive or action.effective_admission.identity_scope
                or not action.effective_admission.read_only):
            raise ValueError('Current action catalog does not prove the canonical read-only Ghidra contract; reservation retained.')
        if (db_access not in (None, 'none') or ghidra_access not in (None, 'query')
                or (db_access is None and ghidra_access is None and not action.ghidra_exclusive)):
            raise ValueError('Provider resource metadata disagrees with the read-only contract; reservation retained.')

        identity = identity_lock_key({'db': live_db()})
        project_key = ghidra_lock_key(params)
        live_record_matches = current is None or (
            current.status == 'failed'
            and current.resource_disposition == 'quarantined'
            and current.execution_attempt == row.get('executionAttempt')
            and current.action_id == row.get('actionId') and current.params == params
            and current.argv == row.get('argv') and current.resource_keys == keys
        )
        checks = {
            'action_is_canonical_read_only_get_references': row.get('actionId') == 'mcp.get-references',
            'only_legacy_database_claim_is_present': bool(identity) and keys == {'identity': identity},
            'database_claim_is_reserved_by_this_job': bool(identity) and store._identity_held.get(identity) == job_id,
            'exact_ghidra_project_is_known': bool(project_key) and project_key != '*',
            'ghidra_project_has_no_other_reservation': bool(project_key) and store._ghidra_held.get(project_key) in (None, job_id),
            'request_does_not_override_database_or_project': (
                not params.get('db') and not params.get('repo') and not params.get('slug')
            ),
            'request_has_exact_program_binding': bool(params.get('locator')) and bool(params.get('programPath') or params.get('program')) and bool(params.get('target')),
            'receipt_records_timed_out_terminal_attempt': (
                'timed out' in str(row.get('error') or '').casefold()
                and row.get('status') == 'failed' and row.get('resourceDisposition') == 'quarantined'
                and bool(row.get('finishedAt')) and bool(row.get('executionAttempt'))
            ),
            'receipt_version_is_current': (
                type(row.get('receiptVersion')) is int and row.get('receiptVersion') >= 1
                and (store._receipt_versions.get(job_id) == row.get('receiptVersion')
                     or (current is None and job_id not in store._receipt_versions))
            ),
            'live_executor_record_matches_receipt': live_record_matches,
        }
        failed_checks = []
        for check_name, passed in checks.items():
            if not passed:
                failed_checks.append(check_name)
        if failed_checks:
            raise ValueError('Narrow reclassification refused; reservation retained. Failed checks: '
                             + ', '.join(failed_checks))

        new_keys = {'ghidra': project_key}
        terminal = dict(row)
        terminal['resourceKeys'] = new_keys
        terminal['resourceDisposition'] = 'quarantined'
        terminal['receiptVersion'] = row['receiptVersion'] + 1
        terminal['resourceReconciliation'] = {
            'trigger': 'dashboard-workflow-control', 'at': time.time(),
            'basisReceiptVersion': row['receiptVersion'],
            'operation': 'reclassify_quarantined_provider_read_claim',
            'fromResourceKeys': dict(keys), 'toResourceKeys': new_keys,
            'proof': 'canonical_get_references_read_only_action_contract',
        }
        # A history-only owner may have no in-memory version entry because
        # startup deliberately does not adopt an executor. Revalidate the
        # exact durable generation immediately before the atomic receipt write.
        if json.loads(path.read_text()) != row:
            raise ValueError('Durable receipt changed during reclassification; reservation retained.')
        with store._persist_lock:
            save_state(path, terminal)
            store._receipt_versions[job_id] = terminal['receiptVersion']
        del store._identity_held[identity]
        store._ghidra_held[project_key] = job_id
        # A receipt-only job has no executor object after server recovery.
        # Reclassify its exact claim under the current read-only contract, but
        # keep it quarantined on Ghidra: this is not process clearance.
        store._retained_unknown_ownership.pop(job_id, None)
        store._retained_policy_mismatches.pop(job_id, None)
        if current is not None:
            current.resource_keys = new_keys
            current.resource_disposition = 'quarantined'
        return {
            'ok': True, 'reclassified': True, 'released': True,
            'jobId': job_id, 'resourceDisposition': 'quarantined',
            'previousResourceKeys': dict(keys), 'resourceKeys': new_keys,
            'receiptVersion': terminal['receiptVersion'],
            'limitations': [
                'The remote Ghidra operation is not proven stopped.',
                'Its project remains quarantined; only the unrelated corpus DB claim was released.',
            ],
        }
