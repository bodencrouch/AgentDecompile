# Failure and continuation

The same projection drives both surfaces, the CLI and agents. Every objective shows its **accepted capabilities, active attempts, independent eligible work, unmet required predicates and next automatic action** (ObjectiveSummary). Diagnosis expands in place; nobody should correlate several logs to learn whether work is progressing.

## Failure record

A FailureRecord shows: stable reason · affected scope · evidence freshness · attempts and budget spent · recovery action · wake condition · the authority needed, only if an external intervention is unavoidable. It carries its lifecycle rail (observed → classified → contained → recovery_pending → reconciling → eligible) and its classification (mismatch, transient, resource, policy).

An escalation (external action required) additionally names the failed predicate, raw evidence references, the independent work still eligible, attempted recoveries and consumed budget, and the exact external change or decision required. It is emitted on meaningful transitions, not on every poll.

## Situations

| Situation | Presentation |
|---|---|
| Deterministic worker error | "Provider paused for this input revision". Show the diagnostic or repair dependency, the tasks that continue and the conditions for automatic resumption. Retry cannot bypass budget or ownership. |
| Slow but advancing attempt | Durable units and the last checkpoint, with a separate heartbeat. No invented percent, no premature no-progress alarm. |
| Ambiguous command outcome | "Checking whether the operation completed". Mutation and retry are disabled for that operation until reconciled; read-only observations stay available. |
| Resource quarantine | Name the occupied resource and the unresolved access evidence. A lease countdown is never a release time. Show independent ready work. |
| Coordinator or store unavailable | The last verified snapshot, visibly dated and read-only; disconnected or unknown freshness. No hidden offline mutations and no fake launch. |
| Missing fixture or capability | The exact missing predicate and the planned compatible producer or alternative. Never a generic red failure. |
| Evidence invalidation | Remove dependent readiness, keep history, explain the changed basis and scheduled revalidation. Coverage may fall. |
| External action required | One deduplicated actionable item with its impact and the independent work still available. Repeat only on material change. Dismissing is not resolution. |
| Policy rollout | The revision and affected scope. Rollback keeps command and acceptance history and never resurrects stale claims or spent budget. |

## Operator actions

Operator actions carry versioned intent IDs through the same admission path as agent actions. Double-click, reconnect and stale-tab requests never create duplicate commands. A stale-version response refreshes the view with an explanation. Cancellation applies to a named scope, keeps independently accepted outputs, and reports unresolved side effects instead of pretending to roll back.

## Containment vocabulary

- **FENCE**: an old generation or changed inputs are historical only; keep the artifact, refuse current acceptance. Fencing does not prove a worker stopped.
- **QUARANTINE**: expired lease or timeout ≠ safe release. Release needs corroborated end of access and owner.
- **CONTINUE**: only ready, fully supplied independent work. A new user message does not reset a retry budget.
- **CONTROL PLANE**: lost decision or acceptance authority pauses new managed mutation in that scope and keeps read-only evidence visible with its age.
