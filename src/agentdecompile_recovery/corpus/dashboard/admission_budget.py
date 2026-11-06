"""Objective admission accounting embedded in the preparation receipt.

Counts dispatch intents, not CPU/tokens/provider usage. Unknown intents stay spent.
"""
from __future__ import annotations


def initialize(row: dict, maximum=None) -> dict:
    if 'objectiveBudget' in row:
        validate(row['objectiveBudget'], row['id'])
        return row['objectiveBudget']
    if maximum is not None and (type(maximum) is not int or maximum < 0):
        raise ValueError('maxActionAdmissions must be a nonnegative integer or null')
    budget = {'schema': 1, 'objectiveId': row['id'], 'maxActionAdmissions': maximum,
              'consumed': 0, 'allocationRevision': 1, 'priorUsageUnknown': bool(row.get('actions')),
              'accountingScope': 'admissions-since-allocation', 'reservations': {}}
    row['objectiveBudget'] = budget
    return budget


def validate(budget: dict, objective_id: str) -> None:
    if not isinstance(budget, dict) or budget.get('schema') != 1 or budget.get('objectiveId') != objective_id:
        raise ValueError('Invalid objective admission accounting identity')
    maximum, consumed = budget.get('maxActionAdmissions'), budget.get('consumed')
    reservations = budget.get('reservations')
    if (maximum is not None and (type(maximum) is not int or maximum < 0)
            or type(consumed) is not int or consumed < 0 or not isinstance(reservations, dict)
            or consumed != len(reservations) or type(budget.get('allocationRevision')) is not int
            or budget['allocationRevision'] < 1 or type(budget.get('priorUsageUnknown')) is not bool):
        raise ValueError('Invalid objective admission accounting counters')
    for key, entry in reservations.items():
        if not isinstance(key, str) or not key or not isinstance(entry, dict) or not entry.get('actionId'):
            raise ValueError('Invalid objective admission reservation')


def reserve(row: dict, dispatch_id: str, action_id: str, action: str) -> dict:
    budget = initialize(row)
    if dispatch_id in budget['reservations']:
        if budget['reservations'][dispatch_id]['actionId'] != action_id:
            raise ValueError('Dispatch reservation identity mismatch')
        return {'nextAction': 'dispatch', 'dispatchId': dispatch_id}
    maximum = budget['maxActionAdmissions']
    if maximum is not None and budget['consumed'] >= maximum:
        return {'nextAction': 'objective_budget_exhausted',
                'reason': 'Objective action-admission allocation exhausted; input or wrapper changes do not reset spending.',
                'wakeCondition': 'explicit_objective_allocation_revision',
                'attemptsSpent': budget['consumed'], 'attemptsRemaining': 0}
    budget['reservations'][dispatch_id] = {'actionId': action_id, 'action': action, 'status': 'intent'}
    budget['consumed'] += 1
    return {'nextAction': 'dispatch', 'dispatchId': dispatch_id}


def acknowledge(row: dict, dispatch_id: str, job_id: str) -> None:
    budget = initialize(row)
    reservation = budget['reservations'][dispatch_id]
    if reservation.get('jobId') not in (None, job_id):
        raise ValueError('Dispatch acknowledged with conflicting job identity')
    reservation.update(status='accepted', jobId=job_id)


def revise(row: dict, *, expected_revision, maximum, unlimited=False) -> dict:
    """Change the allocation, never the already spent admission history."""
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError('expectedAllocationRevision must be a positive integer')
    if type(unlimited) is not bool:
        raise ValueError('unlimited must be a boolean')
    if maximum is None and not unlimited:
        raise ValueError('Null maxActionAdmissions requires explicit unlimited=true')
    if unlimited and maximum is not None:
        raise ValueError('unlimited=true conflicts with finite maxActionAdmissions')
    if maximum is not None and (type(maximum) is not int or maximum < 0):
        raise ValueError('maxActionAdmissions must be a nonnegative integer')
    budget = initialize(row)
    if budget['allocationRevision'] != expected_revision:
        raise ValueError('Allocation revision changed; refresh before revising the allocation')
    budget.setdefault('allocationHistory', []).append({
        'allocationRevision': budget['allocationRevision'],
        'maxActionAdmissions': budget['maxActionAdmissions'],
        'consumedAtRevision': budget['consumed'],
    })
    budget['allocationRevision'] += 1
    budget['maxActionAdmissions'] = maximum
    return budget
