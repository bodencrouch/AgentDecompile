# U9 exact named-obligation extracts

Master SHA256 42bbb486706e529b20007ae0b680509b30d4988cb55612e3f00b46fc8c9f9c44; mechanically copied boundaries from existing named index. Full unit acceptance retains all51 named obligations.


## Master lines 21282–21305: session-contract-2026-09-22:A01

### session-contract-2026-09-22:A01

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Correct bytes with false function label

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A01",
  "requirement": "Correct bytes with false function label",
  "contract_cells": [
    "Binding rejected for identity evidence; independent target accepted"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 326,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21306–21332: session-contract-2026-09-22:A02

### session-contract-2026-09-22:A02

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Withdraw shared donor root

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A02",
  "requirement": "Withdraw shared donor root",
  "contract_cells": [
    "Unsupported descendants stale/export withdrawn; independently rooted claim survives"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 327,
  "status": "partial",
  "evidence_note": "Synthetic staged-source slice (recipient_acceptance.py, 15 tests on the accepted .16 wheel plus a two-file overlay) implements withdrawal: it retires only current acceptances naming a changed dependency, checked against alternate root sets (OR of ANDs), and lists examined/retired explicitly. Retirement is by acceptance id, so a dependency returning to identical content does not revive a retired claim. An independent controller rerun on a fresh stage confirmed 15 passed, exitCode 0, from restored source (the agent's own first \"green\" artifacts were actually a mutation run and are not the basis for this note). No consumer turns a published requires-recipient-acceptance manifest into a real commit yet, and export-reference removal is not wired.",
  "evidence": [
    "/home/brunner56/agentdecompile-deliverables/2026-09-27-p14-recipient-acceptance/report.md"
  ]
}
```


## Master lines 21333–21356: session-contract-2026-09-22:A03

### session-contract-2026-09-22:A03

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Kill compiler after N durable units

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A03",
  "requirement": "Kill compiler after N durable units",
  "contract_cells": [
    "N receipts retained, partial output unpublished; resume without redoing valid N"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 328,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21357–21380: session-contract-2026-09-22:A04

### session-contract-2026-09-22:A04

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Churn child PIDs on identical failing input

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A04",
  "requirement": "Churn child PIDs on identical failing input",
  "contract_cells": [
    "No false progress; one retry owner and finite total attempts"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 329,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21381–21404: session-contract-2026-09-22:A05

### session-contract-2026-09-22:A05

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Hang one device operation

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A05",
  "requirement": "Hang one device operation",
  "contract_cells": [
    "Bounded probe count and responsive coordinator; complete cached task elsewhere finishes"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 330,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21405–21428: session-contract-2026-09-22:A06

### session-contract-2026-09-22:A06

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Omit indirect staged library or fixture

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A06",
  "requirement": "Omit indirect staged library or fixture",
  "contract_cells": [
    "Bundle never launchable; unrelated complete bundle runs"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 331,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21429–21452: session-contract-2026-09-22:A07

### session-contract-2026-09-22:A07

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Late old worker with correct result

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A07",
  "requirement": "Late old worker with correct result",
  "contract_cells": [
    "Private historical result retained, stale acceptance rejected, resource quarantine retained"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 332,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21453–21476: session-contract-2026-09-22:A08

### session-contract-2026-09-22:A08

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Restart coordinator during retry wait

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A08",
  "requirement": "Restart coordinator during retry wait",
  "contract_cells": [
    "Same consumed budget/next eligibility/owner generation; no duplicate launch"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 333,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21477–21500: session-contract-2026-09-22:A09

### session-contract-2026-09-22:A09

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Occupy mutation channel

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A09",
  "requirement": "Occupy mutation channel",
  "contract_cells": [
    "Status observation responds; conflicting mutation waits; independent analysis finishes"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 334,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21501–21524: session-contract-2026-09-22:A10

### session-contract-2026-09-22:A10

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Missing party member/driver/authentication

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A10",
  "requirement": "Missing party member/driver/authentication",
  "contract_cells": [
    "Precise prerequisite task, no behavioral failure falsely recorded"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 335,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21525–21548: session-contract-2026-09-22:A11

### session-contract-2026-09-22:A11

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Recorder fails after successful oracle

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A11",
  "requirement": "Recorder fails after successful oracle",
  "contract_cells": [
    "Behavioral receipt retained, combined success refused; same-action rerun required"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 336,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21549–21572: session-contract-2026-09-22:A12

### session-contract-2026-09-22:A12

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Disconnect after non-idempotent action

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A12",
  "requirement": "Disconnect after non-idempotent action",
  "contract_cells": [
    "Command reconciled or outcome unknown; no automatic duplicate action"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 337,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21573–21596: session-contract-2026-09-22:A13

### session-contract-2026-09-22:A13

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Interrupt destination copy/manifest commit

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A13",
  "requirement": "Interrupt destination copy/manifest commit",
  "contract_cells": [
    "Previous complete manifest usable; no manifest references partial output"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 338,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21597–21620: session-contract-2026-09-22:A14

### session-contract-2026-09-22:A14

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Expired lease but old worker still alive

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A14",
  "requirement": "Expired lease but old worker still alive",
  "contract_cells": [
    "No resource reuse without clearance; disjoint provisioned bundle can proceed"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 339,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21621–21644: session-contract-2026-09-22:A15

### session-contract-2026-09-22:A15

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Near-full swap with qualified small task; spare swap with overloaded class

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A15",
  "requirement": "Near-full swap with qualified small task; spare swap with overloaded class",
  "contract_cells": [
    "First judged on complete admission basis; second refused despite swap capacity"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 340,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21645–21668: session-contract-2026-09-22:A16

### session-contract-2026-09-22:A16

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Large eligible task surrounded by small work

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A16",
  "requirement": "Large eligible task surrounded by small work",
  "contract_cells": [
    "Persisted aging reservation overrides ordinary same-class priority; safe backfill does not delay it; urgent exceptions are visible"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 341,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21669–21695: session-contract-2026-09-22:A17

### session-contract-2026-09-22:A17

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Change acceptance policy/input during verification

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A17",
  "requirement": "Change acceptance policy/input during verification",
  "contract_cells": [
    "Short commit recheck rejects stale proposal; immutable report retained"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 342,
  "status": "partial",
  "evidence_note": "Synthetic staged-source slice (recipient_acceptance.py) covers only the input-generation half: commit() reads the basis, evaluates, then re-reads dependency generations and records stale plus changedDependencies if any moved before the recheck completes. Independent controller rerun confirmed 15 passed, exitCode 0. Policy-revision change during verification (the other half of this contract) is not covered, and there is no durable ledger or short DB write transaction; the recheck is in-memory only.",
  "evidence": [
    "/home/brunner56/agentdecompile-deliverables/2026-09-27-p14-recipient-acceptance/report.md"
  ]
}
```


## Master lines 21696–21719: session-contract-2026-09-22:A18

### session-contract-2026-09-22:A18

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Wrong Lua bridge arguments/config owner/log prefix

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A18",
  "requirement": "Wrong Lua bridge arguments/config owner/log prefix",
  "contract_cells": [
    "Relevant adapter safeguard rejects mutation; read-only status unaffected"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 343,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21720–21743: session-contract-2026-09-22:A19

### session-contract-2026-09-22:A19

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Lose only host/input replica

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A19",
  "requirement": "Lose only host/input replica",
  "contract_cells": [
    "Explicit unavailable dependency, no invented failover; independently replicated task remains eligible"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 344,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21744–21767: session-contract-2026-09-22:A20

### session-contract-2026-09-22:A20

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Shuffle valid proposal completion order

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "A20",
  "requirement": "Shuffle valid proposal completion order",
  "contract_cells": [
    "Same accepted/contested semantic result; arrival order changes no truth decision"
  ],
  "source": "docs/plans/2026-09-22-task-acceptance-and-continuation-design.md",
  "source_line": 345,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21768–21791: session-contract-2026-09-22:FP-01

### session-contract-2026-09-22:FP-01

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-01",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "Correct target bytes under false label: reject semantic binding, accept unrelated independently identified entity."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 225,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21792–21818: session-contract-2026-09-22:FP-02

### session-contract-2026-09-22:FP-02

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-02",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "Withdraw donor root: stale unsupported descendants and export references, preserve independently supported claim and immutable history."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 226,
  "status": "partial",
  "evidence_note": "Synthetic staged-source slice (recipient_acceptance.py) refuses the producer as its own verifier and withdraws a donor root by retiring only unsupported current acceptances while preserving an independently rooted claim; history is immutable because retirement is by acceptance id and re-acceptance gets a new id, never a mutation of the old record. Independent controller rerun confirmed 15 passed, exitCode 0. No durable ledger table exists; the record set is in-memory only, and there is no consumer for a published manifest yet.",
  "evidence": [
    "/home/brunner56/agentdecompile-deliverables/2026-09-27-p14-recipient-acceptance/report.md"
  ]
}
```


## Master lines 21819–21842: session-contract-2026-09-22:FP-03

### session-contract-2026-09-22:FP-03

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Scenario owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-03",
  "requirement": "Scenario owner",
  "contract_cells": [
    "Required party member/module absent: refuse action as prerequisite missing, including a party/object epoch change after preflight; run compatible unrelated fixture."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 227,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21843–21866: session-contract-2026-09-22:FP-04

### session-contract-2026-09-22:FP-04

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Adapter owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-04",
  "requirement": "Adapter owner",
  "contract_cells": [
    "Initialized prefix through recorder and live driver: neither initializes again; fresh isolated prefix follows one bounded setup path."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 228,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21867–21890: session-contract-2026-09-22:FP-05

### session-contract-2026-09-22:FP-05

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Adapter owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-05",
  "requirement": "Adapter owner",
  "contract_cells": [
    "Stale observation connection occupies mutation channel: read-only status remains available; conflicting mutation waits while independent analysis completes."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 229,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21891–21914: session-contract-2026-09-22:FP-06

### session-contract-2026-09-22:FP-06

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Scenario owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-06",
  "requirement": "Scenario owner",
  "contract_cells": [
    "Disconnect after non-idempotent action: reconcile or retain unknown, never replay blindly; unrelated safe read continues."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 230,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21915–21938: session-contract-2026-09-22:FP-07

### session-contract-2026-09-22:FP-07

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-07",
  "requirement": "Coordinator",
  "contract_cells": [
    "Expired old generation returns matching bytes while alive: reject stale publication and retain quarantine; disjoint replacement task can finish."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 231,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21939–21962: session-contract-2026-09-22:FP-08

### session-contract-2026-09-22:FP-08

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Storage owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-08",
  "requirement": "Storage owner",
  "contract_cells": [
    "Source device hangs during copy to healthy destination: partial bundle stays unlaunchable, already complete independent bundle runs; outstanding probes stay bounded."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 232,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21963–21986: session-contract-2026-09-22:FP-09

### session-contract-2026-09-22:FP-09

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Adapter owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-09",
  "requirement": "Adapter owner",
  "contract_cells": [
    "Same deterministic compile failure under new PID: one cached negative and no retry; changed relevant candidate is eligible."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 233,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 21987–22010: session-contract-2026-09-22:FP-10

### session-contract-2026-09-22:FP-10

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-10",
  "requirement": "Coordinator",
  "contract_cells": [
    "Transient provider crash with nested wrapper retries: 100 waiting tasks share one recovery probe and bounded healing/attempt budgets; compatible provider performs independent ready work."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 234,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22011–22034: session-contract-2026-09-22:FP-11

### session-contract-2026-09-22:FP-11

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-11",
  "requirement": "Coordinator",
  "contract_cells": [
    "Repeated zero-goal-delta experiments with unchanged basis: admission stops for that hypothesis; changed evidence-backed strategy and independent task remain eligible."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 235,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22035–22058: session-contract-2026-09-22:FP-12

### session-contract-2026-09-22:FP-12

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Adapter owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-12",
  "requirement": "Adapter owner",
  "contract_cells": [
    "Long legitimate unit has no final report yet: no false failure/progress from PID alone; distinct completed checkpoints count, deadline follows declared lifecycle; short independent task continues."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 236,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22059–22082: session-contract-2026-09-22:FP-13

### session-contract-2026-09-22:FP-13

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-13",
  "requirement": "Coordinator",
  "contract_cells": [
    "Near-full swap with qualified small task, and spare swap with overloaded task: decide from complete profile/pressure/enforcement; admit first when qualified and reject second."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 237,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22083–22106: session-contract-2026-09-22:FP-14

### session-contract-2026-09-22:FP-14

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-14",
  "requirement": "Coordinator",
  "contract_cells": [
    "Large capped-age task surrounded by small high-ordinary-priority tasks: reservation wins within class; non-delaying backfill continues; urgent override history remains visible."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 238,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22107–22130: session-contract-2026-09-22:FP-15

### session-contract-2026-09-22:FP-15

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Scenario owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-15",
  "requirement": "Scenario owner",
  "contract_cells": [
    "Oracle succeeds but video is missing/wrong attempt: preserve behavioral claim, reject combined claim, accept independent complete recorded scenario."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 239,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22131–22154: session-contract-2026-09-22:FP-16

### session-contract-2026-09-22:FP-16

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Storage owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-16",
  "requirement": "Storage owner",
  "contract_cells": [
    "Interrupt destination write/rename/manifest boundary: prior complete export remains readable; no partial reference publishes; unrelated destination can publish."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 240,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22155–22178: session-contract-2026-09-22:FP-17

### session-contract-2026-09-22:FP-17

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-17",
  "requirement": "Coordinator",
  "contract_cells": [
    "Crash after launch intent/budget commit before launch acknowledgment: restart reconciles actual owner, does not duplicate dispatch/charge; independently reconciled task resumes."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 241,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22179–22202: session-contract-2026-09-22:FP-18

### session-contract-2026-09-22:FP-18

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-18",
  "requirement": "Coordinator",
  "contract_cells": [
    "Sole event store unavailable: refuse new acceptance and unsafe dispatch; bounded private checkpoint/read-only cache contract holds; recovery validates continuity before acceptance resumes."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 242,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22203–22226: session-contract-2026-09-22:FP-19

### session-contract-2026-09-22:FP-19

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-19",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "Corrupt one receipt/blob: affected claims quarantined, exact verified restoration or scoped re-verification required; unaffected receipt continues to qualify."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 243,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22227–22250: session-contract-2026-09-22:FP-20

### session-contract-2026-09-22:FP-20

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Storage owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-20",
  "requirement": "Storage owner",
  "contract_cells": [
    "Interrupt schema migration and present old incompatible writer: reject writer, retain old consistent view when supported, resume/finalize once; unrelated compatible read remains available."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 244,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22251–22274: session-contract-2026-09-22:FP-21

### session-contract-2026-09-22:FP-21

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-21",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "Bad policy admits a previously rejected false-label sample: block policy activation; authorized known-good policy retains prior semantics; valid sample still accepts."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 245,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22275–22298: session-contract-2026-09-22:FP-22

### session-contract-2026-09-22:FP-22

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-22",
  "requirement": "Coordinator",
  "contract_cells": [
    "Provider usage unknown after timeout and retry wrapper changes: retain conservative reservation, refuse over-budget launch; independent task with separate valid budget proceeds."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 246,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22299–22322: session-contract-2026-09-22:FP-23

### session-contract-2026-09-22:FP-23

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Adapter owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-23",
  "requirement": "Adapter owner",
  "contract_cells": [
    "Malformed/unknown detector result: classify unknown and quarantine that decision path; qualified alternate adapter or unrelated task continues, no guessed success."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 247,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22323–22346: session-contract-2026-09-22:FP-24

### session-contract-2026-09-22:FP-24

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-24",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "Successful checkpoint combat proposed as full-route/video proof: reject scope promotion, retain checkpoint evidence; correctly scoped unrelated claim accepts."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 248,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22347–22370: session-contract-2026-09-22:FP-25

### session-contract-2026-09-22:FP-25

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-25",
  "requirement": "Coordinator",
  "contract_cells": [
    "Restore backup then receive late events and user continuation: preserve generations/retry lineage and durable wake cursors, reconcile events arriving across subscribe/crash windows without duplicate dispatch/acceptance; ambiguous external effects remain unreplayed until reconciled; do not reset limits; independently reconciled work proceeds."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 249,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22371–22394: session-contract-2026-09-22:FP-26

### session-contract-2026-09-22:FP-26

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-26",
  "requirement": "Coordinator",
  "contract_cells": [
    "Unchanged inputs trigger repeated full-audit pass counter: policy suppresses redundant audit while a declared bounded audit or requested fresh final rebuild still runs; unrelated changed-unit work proceeds."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 251,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22395–22418: session-contract-2026-09-22:FP-27

### session-contract-2026-09-22:FP-27

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Adapter owner

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-27",
  "requirement": "Adapter owner",
  "contract_cells": [
    "CI job denied before start by entitlement: classify external-action-required, no compile failure or local-to-CI promotion; valid local tasks continue and restored entitlement wakes the CI task."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 252,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22419–22442: session-contract-2026-09-22:FP-28

### session-contract-2026-09-22:FP-28

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-28",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "18,578 compiling candidates plus partial receipts proposed as whole-image success: refuse promotion without fresh equality/contribution receipts; scoped compilation facts remain accepted."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 253,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22443–22466: session-contract-2026-09-22:FP-29

### session-contract-2026-09-22:FP-29

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Acceptance authority

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-29",
  "requirement": "Acceptance authority",
  "contract_cells": [
    "Required verifier disappears or two verifiers disagree: proposal waits/contests without producer self-certification; qualified alternate or unrelated independently verified claim proceeds."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 254,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 22467–22490: session-contract-2026-09-22:FP-30

### session-contract-2026-09-22:FP-30

**Owner:** U9. **Requirement disposition:** required. **Original source:** `docs/plans/2026-09-22-session-obligations.json`.

Coordinator

**Active interpretation:** Apply C01–C24 where relevant; all non-conflicting predicates remain required.

The following complete source record retains original acceptance, dependency, successor and historical evidence fields. Its status is historical, not a fresh result.

```json
{
  "id": "FP-30",
  "requirement": "Coordinator",
  "contract_cells": [
    "Canary exceeds predeclared cost/duration or error threshold: automatic preauthorized routing rollback preserves budgets/evidence and acceptance policy; baseline eligible work continues."
  ],
  "source": "docs/plans/2026-09-22-failure-prevention-and-recovery-contracts.md",
  "source_line": 255,
  "status": "unverified",
  "evidence_note": "Design exists; complete implementation and required acceptance evidence remain open."
}
```


## Master lines 24897–24904: autonomous-roadmap-2026-09-22:M0

### autonomous-roadmap-2026-09-22:M0

**Owner:** U9. **Requirement disposition:** required. **Source:** `docs/plans/2026-09-22-autonomous-capability-product-roadmap.md`:143. Apply C01–C24; historical checked status is not fresh acceptance.

```text
| M0 Reliable continuation | Existing preparation/recovery retains attempts, reports exact next step and avoids repeated unchanged failures across resume | Real coordinator tests and isolated child-process checks; no claim of autonomous live game delivery |
```
