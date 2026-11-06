"""Durable dashboard MCP tools/call intent accounting (not provider internals)."""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from contextlib import contextmanager


class DispatchRefused(Exception):
    def __init__(self, decision):
        self.decision = decision
        super().__init__(decision['reason'])


_GUARD = ContextVar('preparation_mcp_dispatch_guard', default=None)


@contextmanager
def dispatch_scope(reserve):
    state = {'reserve': reserve, 'dispatched': 0, 'unknown': False}
    token = _GUARD.set(state)
    try:
        yield state
    finally:
        _GUARD.reset(token)


def before_dispatch(tool):
    state = _GUARD.get()
    if state is not None and state['unknown']:
        raise DispatchRefused({
            'nextAction': 'provider_ownership_unresolved',
            'reason': 'An earlier MCP dispatch has unresolved ownership; reconcile before another dispatch.',
            'wakeCondition': 'explicit_owner_reconciliation',
        })
    if state is not None and state['reserve'] is not None:
        state['reserve'](tool)
        state['dispatched'] += 1


def observe(result):
    state = _GUARD.get()
    if state is not None and (result.get('ownershipUnresolved') or result.get('ownershipResolved') is False):
        state['unknown'] = True


def initialize(row, maximum=None):
    if 'providerBudget' not in row:
        if maximum is not None and (type(maximum) is not int or maximum < 0):
            raise ValueError('maxMcpToolCalls must be a nonnegative integer or null')
        row['providerBudget'] = {
            'schema': 1, 'objectiveId': row['id'], 'maxMcpToolCalls': maximum,
            'consumed': 0, 'allocationRevision': 1,
            'priorUsageUnknown': bool(row.get('actions')),
            'accountingScope': 'mcp-tool-dispatches-since-allocation', 'reservations': {},
        }
    budget = row['providerBudget']
    if (not isinstance(budget, dict) or budget.get('schema') != 1
            or budget.get('objectiveId') != row['id']
            or budget.get('accountingScope') != 'mcp-tool-dispatches-since-allocation'
            or type(budget.get('consumed')) is not int or budget['consumed'] < 0
            or not isinstance(budget.get('reservations'), dict)
            or budget['consumed'] != len(budget['reservations'])
            or type(budget.get('allocationRevision')) is not int or budget['allocationRevision'] < 1
            or type(budget.get('priorUsageUnknown')) is not bool
            or (budget.get('maxMcpToolCalls') is not None and
                (type(budget['maxMcpToolCalls']) is not int or budget['maxMcpToolCalls'] < 0))):
        raise ValueError('Invalid MCP dispatch accounting')
    for attempt, entry in budget['reservations'].items():
        if not isinstance(attempt, str) or not attempt or not isinstance(entry, dict) or not entry.get('tool') or entry.get('status') != 'intent':
            raise ValueError('Invalid MCP dispatch reservation')
    return budget


def public(row):
    budget = initialize(row)
    result = {key: budget[key] for key in ('schema', 'objectiveId', 'maxMcpToolCalls',
        'consumed', 'allocationRevision', 'priorUsageUnknown', 'accountingScope')}
    result['remaining'] = None if budget['maxMcpToolCalls'] is None else max(0, budget['maxMcpToolCalls'] - budget['consumed'])
    return result


def exhausted(row):
    budget = initialize(row)
    if budget['maxMcpToolCalls'] is None or budget['consumed'] < budget['maxMcpToolCalls']:
        return None
    return {'nextAction': 'provider_budget_exhausted',
            'reason': 'MCP tool-dispatch allocation exhausted; revise the provider allocation explicitly to continue.',
            'wakeCondition': 'explicit_provider_allocation_revision',
            'attemptsSpent': budget['consumed'], 'attemptsRemaining': 0,
            'allocationRevision': budget['allocationRevision']}


def reserve(row, tool, *, dispatch_id=None, action_id=None):
    decision = exhausted(row)
    if decision:
        raise DispatchRefused(decision)
    budget = initialize(row)
    attempt = uuid.uuid4().hex
    budget['reservations'][attempt] = {'tool': tool, 'status': 'intent', 'parentDispatchId': dispatch_id, 'actionId': action_id}
    budget['consumed'] += 1
    return attempt


def revise(row, *, expected_revision, maximum, unlimited=False):
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError('expectedAllocationRevision must be a positive integer')
    if type(unlimited) is not bool or (maximum is None and not unlimited) or (maximum is not None and unlimited):
        raise ValueError('Supply a finite maxMcpToolCalls or explicit unlimited=true')
    if maximum is not None and (type(maximum) is not int or maximum < 0):
        raise ValueError('maxMcpToolCalls must be a nonnegative integer')
    budget = initialize(row)
    if budget['allocationRevision'] != expected_revision:
        raise ValueError('Provider allocation revision changed; refresh before revising')
    budget.setdefault('allocationHistory', []).append({
        'allocationRevision': budget['allocationRevision'], 'maxMcpToolCalls': budget['maxMcpToolCalls'],
        'consumedAtRevision': budget['consumed']})
    budget['allocationRevision'] += 1
    budget['maxMcpToolCalls'] = maximum
    return budget
